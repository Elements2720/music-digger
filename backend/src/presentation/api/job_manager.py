"""One-job-at-a-time background runner with SSE progress broadcasting.

The API keeps a single shared :class:`~container.Container` alive for the whole
server process (warm CLAP model, single SQLite/LanceDB owner). This manager
runs long use cases as ``asyncio.Task`` objects over that shared container and
streams their synchronous progress callbacks to every connected browser.

Turbo mode is scoped per job: the shared embedder/decoder are adjusted before
the run and restored in ``finally``. No environment variables are mutated and
no second container is built.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from domain.use_cases import DEFAULT_TECHNO_TERMS, IndexCatalog

from .schemas import set_summary_payload

LOGGER = logging.getLogger(__name__)

_QUEUE_MAXSIZE = 256
_HEARTBEAT_SECONDS = 15.0
_UNLIMITED = 10**9
_TURBO_BATCH_SIZE = 48
_TURBO_CONCURRENCY = 24
_TURBO_CPU_WORKERS = 10
_TURBO_QUEUE_MAXSIZE = 128


class JobConflictError(Exception):
    """A job is already running."""


class JobParamError(ValueError):
    """A job was requested with invalid parameters."""


@dataclass
class JobState:
    """Mutable state of the current (or last) job."""

    kind: str
    params: dict[str, Any]
    status: str = "running"
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    stage: str = "starting"
    message: str = ""
    processed: int = 0
    failed: int = 0
    total: int | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "params": self.params,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "stage": self.stage,
            "message": self.message,
            "processed": self.processed,
            "failed": self.failed,
            "total": self.total,
            "result": self.result,
            "error": self.error,
        }


class JobManager:
    """Runs one long use case at a time and fans progress out to SSE clients."""

    def __init__(
        self,
        get_container: Callable[[], Any],
        *,
        index_factory: Callable[..., Any] = IndexCatalog,
    ) -> None:
        self._get_container = get_container
        self._index_factory = index_factory
        self._job: JobState | None = None
        self._task: asyncio.Task[None] | None = None
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._started_monotonic = 0.0

    # ------------------------------------------------------------------ state

    @property
    def active(self) -> bool:
        return self._task is not None and not self._task.done()

    def snapshot(self) -> dict[str, Any] | None:
        return self._job.snapshot() if self._job is not None else None

    # --------------------------------------------------------------- control

    async def start(self, kind: str, params: dict[str, Any]) -> dict[str, Any]:
        """Validate parameters and launch the job task."""
        if self.active:
            raise JobConflictError("a job is already running")
        config = self._validate(kind, params)

        job = JobState(kind=kind, params=config)
        self._job = job
        self._started_monotonic = time.monotonic()
        self._task = asyncio.create_task(
            self._run(job, config), name=f"dig-job:{kind}"
        )
        LOGGER.info("job %s started with %s", kind, config)
        return job.snapshot()

    async def cancel(self) -> bool:
        """Request cancellation of the active task; False when idle."""
        if not self.active:
            return False
        assert self._task is not None
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        job = self._job
        if job is not None and job.status == "running":
            # Cancelled before the coroutine's first step: ``_run`` never got
            # to its ``finally``, so settle the state here.
            job.status = "cancelled"
            job.finished_at = time.time()
            self._emit_final(job)
        return True

    async def wait(self) -> None:
        """Await the active task (used by tests and graceful shutdown)."""
        if self._task is not None:
            await asyncio.gather(self._task, return_exceptions=True)

    # ------------------------------------------------------------- SSE stream

    async def stream(self, request: Any) -> AsyncIterator[str]:
        """Yield SSE frames: state snapshot, progress events, heartbeats."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=_QUEUE_MAXSIZE
        )
        self._subscribers.add(queue)
        try:
            yield _sse({"type": "state", "job": self.snapshot()})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=_HEARTBEAT_SECONDS
                    )
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                yield _sse(event)
                if event.get("type") in {"done", "error", "cancelled"}:
                    break
        finally:
            self._subscribers.discard(queue)

    # ----------------------------------------------------------------- runner

    async def _run(self, job: JobState, config: dict[str, Any]) -> None:
        try:
            container = self._get_container()
            if container is None:
                raise RuntimeError("the service container is not ready yet")
            runner = getattr(self, f"_run_{job.kind.replace('-', '_')}")
            await runner(job, container, config)
            job.status = "done"
        except asyncio.CancelledError:
            job.status = "cancelled"
            raise
        except Exception as exc:
            LOGGER.exception("job %s failed", job.kind)
            job.status = "error"
            job.error = str(exc) or type(exc).__name__
        finally:
            job.finished_at = time.time()
            self._emit_final(job)

    async def _run_index(
        self, job: JobState, container: Any, config: dict[str, Any]
    ) -> None:
        repository = container.track_repository
        limit = config["limit"] or _UNLIMITED
        if config["reindex"]:
            estimate = await repository.count()
        else:
            estimate = await repository.count() - await repository.count_embedded()
        job.total = min(estimate, limit) if limit < _UNLIMITED else estimate

        embedder = container.clap_embedder
        decoder = container.audio_decoder
        default_batch = container.settings.clap_batch_size
        default_concurrency = container.settings.preview_concurrency
        catalog = container.index_catalog
        turbo = config["turbo"]

        try:
            if turbo:
                embedder.batch_size = _TURBO_BATCH_SIZE
                decoder.set_concurrency(_TURBO_CONCURRENCY)
                catalog = self._index_factory(
                    track_repository=repository,
                    audio_decoder=decoder,
                    feature_extractor=container.feature_extractor,
                    audio_embedder=embedder,
                    cpu_workers=_TURBO_CPU_WORKERS,
                    queue_maxsize=_TURBO_QUEUE_MAXSIZE,
                )

            def on_progress(event: Any) -> None:
                elapsed = max(time.monotonic() - self._started_monotonic, 1e-6)
                self._progress(
                    job,
                    stage="indexing",
                    processed=event.processed,
                    failed=event.failed,
                    speed=round(event.processed / elapsed, 2),
                    memory=self._memory(container),
                )

            result = await catalog.execute(
                limit=limit,
                batch_size=_TURBO_BATCH_SIZE if turbo else config["batch_size"],
                max_failures=_UNLIMITED if config["retry_failed"] else 3,
                reindex=config["reindex"],
                progress=on_progress,
            )
            job.result = {
                "processed": result.processed,
                "failed": result.failed,
                "embedded_total": result.embedded_total,
            }
        finally:
            if turbo:
                embedder.batch_size = default_batch
                decoder.set_concurrency(default_concurrency)

    async def _run_seed_crawl(
        self, job: JobState, container: Any, config: dict[str, Any]
    ) -> None:
        job.stage = "crawling Deezer"
        total = config["electronic_limit"] + config["general_limit"]
        job.total = total

        def on_progress(event: Any) -> None:
            stage = "crawling Deezer" if event.stage == "electronic" else event.stage
            self._progress(
                job,
                stage=stage,
                processed=event.found,
                total=total,
                message=event.name,
                memory=self._memory(container),
            )

        result = await container.build_seed_list.execute(
            electronic_limit=config["electronic_limit"],
            general_limit=config["general_limit"],
            max_depth=config["max_depth"],
            use_deezer=True,
            progress=on_progress,
        )
        job.result = _seed_result(result)

    async def _run_seed_llm(
        self, job: JobState, container: Any, config: dict[str, Any]
    ) -> None:
        job.stage = "asking the LLM"
        job.message = f"{config['count']} artists for {', '.join(config['genres'])}"
        result = await container.build_seed_list.execute(
            use_deezer=False,
            llm_genres=tuple(config["genres"]),
            llm_count=config["count"],
        )
        job.result = _seed_result(result)

    async def _run_seed_itunes(
        self, job: JobState, container: Any, config: dict[str, Any]
    ) -> None:
        job.stage = "crawling iTunes keywords"
        job.total = len(config["terms"])

        def on_progress(term: str, index: int, total: int, tracks_found: int) -> None:
            self._progress(
                job,
                stage="crawling iTunes keywords",
                processed=index - 1,
                total=total,
                message=f"{term} - {tracks_found} tracks",
                memory=self._memory(container),
            )

        result = await container.crawl_itunes_seeds.execute(
            terms=config["terms"],
            tracks_per_term=config["tracks_per_term"],
            expand_compilations=config["expand_compilations"],
            save_tracks=config["save_tracks"],
            progress=on_progress,
        )
        job.result = {
            "terms_processed": result.terms_processed,
            "terms_failed": result.terms_failed,
            "tracks_found": result.tracks_found,
            "tracks_saved": result.tracks_saved,
            "artists_discovered": result.artists_discovered,
        }

    async def _run_fetch_metadata(
        self, job: JobState, container: Any, config: dict[str, Any]
    ) -> None:
        job.stage = "fetching iTunes metadata"
        job.total = config["artists_limit"]

        def on_progress(seed: Any, index: int, total: int) -> None:
            self._progress(
                job,
                stage="fetching metadata",
                processed=max(0, index - 1),
                total=total,
                message=seed.name,
                memory=self._memory(container),
            )

        result = await container.fetch_catalog_metadata.execute(
            artists_limit=config["artists_limit"],
            tracks_per_artist=config["tracks_per_artist"],
            retry_failed=config["retry_failed"],
            progress=on_progress,
        )
        job.result = {
            "artists_processed": result.artists_processed,
            "artists_failed": result.artists_failed,
            "artists_skipped": result.artists_skipped,
            "tracks_found": result.tracks_found,
            "tracks_saved": result.tracks_saved,
        }

    async def _run_analyze_set(
        self, job: JobState, container: Any, config: dict[str, Any]
    ) -> None:
        downloader = container.set_downloader
        settings = container.settings
        cookies_file = (
            Path(config["cookies_file"]) if config["cookies_file"] else None
        )
        downloader.set_cookie_overrides(
            cookies_file=cookies_file,
            cookies_from_browser=config["cookies_from_browser"],
        )
        try:

            def on_progress(event: Any) -> None:
                self._progress(
                    job,
                    stage=event.stage,
                    processed=event.completed,
                    total=event.total or None,
                    message=event.message,
                    memory=self._memory(container),
                )

            dj_set = await container.analyze_dj_set.execute(
                config["source"],
                destination_dir=settings.set_cache_dir,
                use_shazam=config["shazam"],
                use_comments=config["comments"],
                keep_audio=config["keep_audio"],
                progress=on_progress,
            )
            job.result = {"set": set_summary_payload(dj_set)}
        finally:
            downloader.set_cookie_overrides(
                cookies_file=settings.ytdlp_cookies_file,
                cookies_from_browser=settings.ytdlp_cookies_from_browser,
            )

    # ---------------------------------------------------------------- helpers

    def _progress(
        self,
        job: JobState,
        *,
        stage: str,
        processed: int,
        failed: int = 0,
        total: int | None = None,
        message: str = "",
        speed: float | None = None,
        memory: dict[str, Any] | None = None,
    ) -> None:
        job.stage = stage
        job.processed = processed
        job.failed = failed
        if total is not None:
            job.total = total
        job.message = message
        self._emit(
            {
                "type": "progress",
                "job": job.snapshot(),
                "speed": speed,
                "memory": memory,
            }
        )

    def _memory(self, container: Any) -> dict[str, Any] | None:
        probe = getattr(container, "hardware_probe", None)
        if probe is None:
            return None
        try:
            info = probe.probe()
        except Exception:
            LOGGER.debug("hardware probe failed during a job", exc_info=True)
            return None
        return {
            "vram_free_mb": info.vram_free_mb,
            "vram_total_mb": info.vram_total_mb,
            "ram_free_mb": info.ram_free_mb,
            "ram_total_mb": info.ram_total_mb,
        }

    def _emit(self, event: dict[str, Any]) -> None:
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                LOGGER.debug("dropping SSE event for a slow client")

    def _emit_final(self, job: JobState) -> None:
        event_type = {
            "done": "done",
            "error": "error",
            "cancelled": "cancelled",
        }.get(job.status, "state")
        self._emit(
            {
                "type": event_type,
                "job": job.snapshot(),
                "result": job.result,
                "message": job.error,
            }
        )

    # ------------------------------------------------------------- validation

    def _validate(self, kind: str, params: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(params, dict):
            raise JobParamError("params must be an object")
        validators = {
            "index": self._validate_index,
            "seed-crawl": self._validate_seed_crawl,
            "seed-llm": self._validate_seed_llm,
            "seed-itunes": self._validate_seed_itunes,
            "fetch-metadata": self._validate_fetch_metadata,
            "analyze-set": self._validate_analyze_set,
        }
        validator = validators.get(kind)
        if validator is None:
            raise JobParamError(f"unknown job kind {kind!r}")
        return validator(params)

    @staticmethod
    def _validate_index(params: dict[str, Any]) -> dict[str, Any]:
        return {
            "limit": _as_int(params, "limit", 500, minimum=0),
            "batch_size": _as_int(params, "batch_size", 16, minimum=1, maximum=48),
            "turbo": _as_bool(params, "turbo", False),
            "reindex": _as_bool(params, "reindex", False),
            "retry_failed": _as_bool(params, "retry_failed", False),
        }

    @staticmethod
    def _validate_seed_crawl(params: dict[str, Any]) -> dict[str, Any]:
        return {
            "electronic_limit": _as_int(
                params, "electronic_limit", 1000, minimum=0
            ),
            "general_limit": _as_int(params, "general_limit", 300, minimum=0),
            "max_depth": _as_int(params, "max_depth", 2, minimum=0, maximum=5),
        }

    @staticmethod
    def _validate_seed_llm(params: dict[str, Any]) -> dict[str, Any]:
        raw_genre = params.get("genre", "")
        if not isinstance(raw_genre, str) or not raw_genre.strip():
            raise JobParamError("genre must be a non-empty string")
        genres = [part.strip() for part in raw_genre.split(",") if part.strip()]
        return {
            "genre": raw_genre.strip(),
            "genres": genres,
            "count": _as_int(params, "count", 100, minimum=1, maximum=1000),
        }

    @staticmethod
    def _validate_seed_itunes(params: dict[str, Any]) -> dict[str, Any]:
        raw_terms = params.get("terms")
        if raw_terms is None:
            terms: tuple[str, ...] = DEFAULT_TECHNO_TERMS
        elif isinstance(raw_terms, str):
            parts = [p.strip() for p in raw_terms.split(",") if p.strip()]
            if not parts:
                raise JobParamError("terms must not be empty")
            terms = tuple(parts)
        elif isinstance(raw_terms, (list, tuple)):
            if len(raw_terms) == 0:
                raise JobParamError("terms must not be empty")
            parts = []
            for item in raw_terms:
                if not isinstance(item, str) or not item.strip():
                    raise JobParamError("terms must contain non-empty strings")
                parts.append(item.strip())
            terms = tuple(parts)
        else:
            raise JobParamError(
                "terms must be a list of strings or comma-separated string"
            )

        return {
            "terms": terms,
            "tracks_per_term": _as_int(
                params, "tracks_per_term", 200, minimum=1, maximum=200
            ),
            "expand_compilations": _as_bool(params, "expand_compilations", True),
            "save_tracks": _as_bool(params, "save_tracks", True),
        }

    @staticmethod
    def _validate_fetch_metadata(params: dict[str, Any]) -> dict[str, Any]:
        return {
            "artists_limit": _as_int(
                params, "artists_limit", 50, minimum=1, maximum=5000
            ),
            "tracks_per_artist": _as_int(
                params, "tracks_per_artist", 200, minimum=1, maximum=200
            ),
            "retry_failed": _as_bool(params, "retry_failed", False),
        }

    @staticmethod
    def _validate_analyze_set(params: dict[str, Any]) -> dict[str, Any]:
        source = params.get("source", "")
        if not isinstance(source, str) or not source.strip():
            raise JobParamError("source must be a URL or a local audio file path")
        cookies_file = params.get("cookies_file")
        if cookies_file is not None and (
            not isinstance(cookies_file, str) or not cookies_file.strip()
        ):
            raise JobParamError("cookies_file must be a path or null")
        cookies_browser = params.get("cookies_from_browser")
        if cookies_browser is not None and (
            not isinstance(cookies_browser, str) or not cookies_browser.strip()
        ):
            raise JobParamError("cookies_from_browser must be a browser name or null")
        return {
            "source": source.strip(),
            "shazam": _as_bool(params, "shazam", True),
            "comments": _as_bool(params, "comments", True),
            "keep_audio": _as_bool(params, "keep_audio", False),
            "cookies_file": cookies_file.strip() if cookies_file else None,
            "cookies_from_browser": (
                cookies_browser.strip() if cookies_browser else None
            ),
        }


def _seed_result(result: Any) -> dict[str, int]:
    return {
        "discovered": result.discovered,
        "llm_generated": result.llm_generated,
        "written": result.written,
        "electronic_total": result.electronic_total,
        "general_total": result.general_total,
    }


def _as_int(
    params: dict[str, Any],
    key: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = params.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise JobParamError(f"{key} must be an integer")
    if minimum is not None and raw < minimum:
        raise JobParamError(f"{key} must be at least {minimum}")
    if maximum is not None and raw > maximum:
        raise JobParamError(f"{key} must be at most {maximum}")
    return raw


def _as_bool(params: dict[str, Any], key: str, default: bool) -> bool:
    raw = params.get(key, default)
    if not isinstance(raw, bool):
        raise JobParamError(f"{key} must be a boolean")
    return raw


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


__all__ = [
    "JobConflictError",
    "JobManager",
    "JobParamError",
    "JobState",
]
