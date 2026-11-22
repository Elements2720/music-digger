"""Use case: analyze a full DJ set into passages, IDs, and matches.

Pipeline (memory-bounded for 16 GB RAM / 6 GB VRAM):

1. ``ISetDownloader.fetch_set`` resolves a URL or local file to audio on disk
   (downloaded files land in the storage cache and are marked temporary).
2. ``IAudioSegmenter.detect_passages`` streams a 16 kHz mono view to find
   musically coherent passages — the full set is never decoded into RAM.
3. For every passage, only a clean 30 s window from its middle (skipping
   crossfade edges) is decoded at a time; BPM/key extraction runs on the
   bounded CPU pool and the 30 s buffers are embedded on GPU in FP16
   micro-batches, then released immediately.
4. Exact IDs come from two sources: comment timestamps parsed by the local
   LLM (matched within ±45 s of a passage) and async fingerprinting
   (Shazam) for passages the comments could not name.
5. Every passage — including unreleased "no-ID" ones — gets its closest
   catalog tracks within ±5 BPM (DigDeeper's "closest we found").
6. The set's tempo range and L2-normalized mean embedding are persisted
   through ``ISetRepository``; discovered artist names snowball into the seed
   list; the temporary download is deleted unless ``keep_audio`` is set.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
from collections.abc import Callable, Sequence
from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ..entities.dj_set import DJSet, DownloadedSet, Passage, TrackMatch
from ..entities.search import SearchFilter
from ..entities.track import SeedArtist, TrackReference
from ..interfaces.audio_engine import (
    IAudioDecoder,
    IAudioEmbedder,
    IAudioSegmenter,
    IFeatureExtractor,
    IFingerprinter,
    ISetDownloader,
)
from ..interfaces.llm import ILLMService
from ..interfaces.repositories import ISeedRepository, ISetRepository, ITrackRepository
from ..value_objects.audio_features import (
    BPM,
    BPM_MAX,
    BPM_MIN,
    AudioFeatures,
    EmbeddingVector,
    TimeRange,
)

LOGGER = logging.getLogger(__name__)

#: GPU micro-batch ceiling for the 6 GB card (AnalysisBatch rule from AGENTS).
MAX_EMBED_BATCH = 16
DEFAULT_CORE_WINDOW_SECONDS = 30.0
DEFAULT_SNIPPET_SECONDS = 12.0
DEFAULT_BPM_MATCH_TOLERANCE = 5.0
DEFAULT_ID_MATCH_TOLERANCE_SECONDS = 45.0
DEFAULT_MAX_MATCHES_PER_PASSAGE = 5
#: Snowball priority for artists discovered inside DJ sets.
DISCOVERY_PRIORITY = 0.9


@dataclass(frozen=True, slots=True)
class AnalyzeEvent:
    """Progress event emitted at each pipeline stage."""

    stage: str
    completed: int
    total: int
    message: str = ""
    failed: int = 0


class AnalyzeDJSet:
    """Analyze one DJ set end-to-end and persist it for set-to-set digging."""

    def __init__(
        self,
        *,
        set_downloader: ISetDownloader,
        audio_segmenter: IAudioSegmenter,
        audio_decoder: IAudioDecoder,
        feature_extractor: IFeatureExtractor,
        audio_embedder: IAudioEmbedder,
        track_repository: ITrackRepository,
        set_repository: ISetRepository,
        seed_repository: ISeedRepository,
        fingerprinter: IFingerprinter | None = None,
        llm_service: ILLMService | None = None,
        cpu_executor: Executor | None = None,
        cpu_workers: int = 4,
        embed_batch_size: int = MAX_EMBED_BATCH,
        core_window_seconds: float = DEFAULT_CORE_WINDOW_SECONDS,
        snippet_seconds: float = DEFAULT_SNIPPET_SECONDS,
        bpm_match_tolerance: float = DEFAULT_BPM_MATCH_TOLERANCE,
        id_match_tolerance_seconds: float = DEFAULT_ID_MATCH_TOLERANCE_SECONDS,
        max_matches_per_passage: int = DEFAULT_MAX_MATCHES_PER_PASSAGE,
    ) -> None:
        if cpu_workers < 1:
            raise ValueError("cpu_workers must be at least 1")
        if not 1 <= embed_batch_size <= MAX_EMBED_BATCH:
            raise ValueError(
                f"embed_batch_size must be between 1 and {MAX_EMBED_BATCH}"
            )
        if core_window_seconds <= 0 or snippet_seconds <= 0:
            raise ValueError("window sizes must be positive")
        self._set_downloader = set_downloader
        self._audio_segmenter = audio_segmenter
        self._audio_decoder = audio_decoder
        self._feature_extractor = feature_extractor
        self._audio_embedder = audio_embedder
        self._track_repository = track_repository
        self._set_repository = set_repository
        self._seed_repository = seed_repository
        self._fingerprinter = fingerprinter
        self._llm_service = llm_service
        self._cpu_executor = cpu_executor
        self._cpu_workers = cpu_workers
        self._embed_batch_size = embed_batch_size
        self._core_window_seconds = core_window_seconds
        self._snippet_seconds = snippet_seconds
        self._bpm_tolerance = bpm_match_tolerance
        self._id_tolerance = id_match_tolerance_seconds
        self._max_matches = max_matches_per_passage

    async def execute(
        self,
        source: str,
        *,
        destination_dir: Path,
        use_shazam: bool = True,
        use_comments: bool = True,
        keep_audio: bool = False,
        progress: Callable[[AnalyzeEvent], None] | None = None,
    ) -> DJSet:
        """Analyze ``source`` and return the persisted :class:`DJSet`."""
        if self._fingerprinter is not None and hasattr(
            self._fingerprinter, "reset_circuit_breaker"
        ):
            self._fingerprinter.reset_circuit_breaker()
        downloaded = await self._set_downloader.fetch_set(
            source, destination_dir, fetch_comments=use_comments
        )
        self._notify(progress, "download", 1, 1, downloaded.title)

        try:
            if downloaded.duration_seconds is None:
                raise ValueError(
                    "the downloaded set has no duration; cannot segment it"
                )
            duration = downloaded.duration_seconds

            if self._fingerprinter is not None and hasattr(
                self._fingerprinter, "reset_circuit_breaker"
            ):
                self._fingerprinter.reset_circuit_breaker()

            ranges = await asyncio.to_thread(
                self._audio_segmenter.detect_passages,
                downloaded.audio_path,
                duration,
            )
            if not ranges:
                ranges = (TimeRange(0.0, duration),)
            self._notify(
                progress, "segment", len(ranges), len(ranges), f"{len(ranges)} passages"
            )

            own_executor = self._cpu_executor is None
            executor = self._cpu_executor or ProcessPoolExecutor(
                max_workers=self._cpu_workers
            )
            try:
                passages = await self._analyze_passages(
                    downloaded, ranges, executor, progress
                )
                passages = await self._identify_passages(
                    downloaded,
                    passages,
                    use_shazam=use_shazam,
                    use_comments=use_comments,
                    progress=progress,
                )
            finally:
                if own_executor:
                    executor.shutdown(wait=True)

            dj_set = self._build_set(source, downloaded, passages)
            await self._set_repository.save(dj_set)
            self._notify(progress, "persist", 1, 1, dj_set.id)
            await self._snowball(passages, downloaded)
            return dj_set
        finally:
            if downloaded.is_temporary and not keep_audio:
                await asyncio.to_thread(_delete_quietly, downloaded.audio_path)

    # --------------------------------------------------------- core windows

    def _core_window(self, passage_range: TimeRange) -> TimeRange:
        """Clean 30 s window centered in the passage (crossfades skipped)."""
        span = passage_range.duration_seconds
        window = min(self._core_window_seconds, span)
        middle = passage_range.start_seconds + span / 2.0
        start = middle - window / 2.0
        return TimeRange(start, start + window)

    async def _analyze_passages(
        self,
        downloaded: DownloadedSet,
        ranges: Sequence[TimeRange],
        executor: Executor,
        progress: Callable[[AnalyzeEvent], None] | None,
    ) -> list[Passage]:
        """Decode/extract/embed in chunks so RAM holds one batch of windows."""
        loop = asyncio.get_running_loop()
        passages: list[Passage] = []
        extract_completed = 0
        embed_completed = 0
        total_passages = len(ranges)

        for chunk_start in range(0, total_passages, self._embed_batch_size):
            chunk = list(ranges[chunk_start : chunk_start + self._embed_batch_size])
            buffers = []
            for passage_range in chunk:
                core = self._core_window(passage_range)
                buffers.append(
                    await self._audio_decoder.decode_segment(
                        downloaded.audio_path,
                        core,
                        sample_rate=48_000,
                        channels=1,
                    )
                )

            tasks = [
                loop.run_in_executor(executor, self._feature_extractor.extract, b)
                for b in buffers
            ]
            features: list[Any] = []
            for p_range, fut in zip(chunk, tasks):
                try:
                    feature = await fut
                except Exception as exc:  # noqa: BLE001
                    feature = exc
                features.append(feature)
                extract_completed += 1
                extracted = _coerce_features(feature)
                bpm_str = f"{extracted.bpm.value:.0f} BPM" if extracted.bpm else "? BPM"
                key_str = f", {extracted.key.notation}" if extracted.key else ""
                self._notify(
                    progress,
                    "extract",
                    extract_completed,
                    total_passages,
                    f"{_range_label(p_range)} ({bpm_str}{key_str})",
                )

            vectors = await asyncio.to_thread(self._audio_embedder.embed_batch, buffers)
            # PCM is dead the moment embeddings exist.
            buffers.clear()

            chunk_passages: list[Passage] = []
            for p_range, feature, vector in zip(chunk, features, vectors):
                extracted = _coerce_features(feature)
                passage = Passage(
                    time_range=p_range,
                    bpm=extracted.bpm,
                    key=extracted.key,
                    embedding=vector,
                )
                chunk_passages.append(passage)
                embed_completed += 1
                self._notify(
                    progress,
                    "embed",
                    embed_completed,
                    total_passages,
                    _range_label(p_range),
                )

            passages.extend(chunk_passages)
            await self._attach_closest_matches(
                passages,
                start=len(passages) - len(chunk_passages),
                progress=progress,
                total=total_passages,
            )
        return passages

    async def _attach_closest_matches(
        self,
        passages: list[Passage],
        *,
        start: int,
        progress: Callable[[AnalyzeEvent], None] | None = None,
        total: int | None = None,
    ) -> None:
        """Fill each new passage's top catalog matches within ±5 BPM."""
        total_count = total or len(passages)
        for index in range(start, len(passages)):
            passage = passages[index]
            matches: tuple[TrackMatch, ...] = ()
            if passage.embedding is not None:
                try:
                    matches = await self._find_closest(passage)
                except Exception:
                    LOGGER.exception(
                        "closest-track lookup failed for %s", passage.time_range
                    )
            if matches:
                passages[index] = replace(passage, closest_matches=matches)
                top = matches[0]
                detail = f": top {top.track.display_name} ({top.similarity_percent:.0f}%)"
            else:
                detail = ": no close match"
            self._notify(
                progress,
                "match",
                index + 1,
                total_count,
                f"{_range_label(passage.time_range)}{detail}",
            )

    async def _find_closest(self, passage: Passage) -> tuple[TrackMatch, ...]:
        assert passage.embedding is not None
        bpm_min: float | None = None
        bpm_max: float | None = None
        if passage.bpm is not None:
            bpm_min = max(BPM_MIN, passage.bpm.value - self._bpm_tolerance)
            bpm_max = min(BPM_MAX, passage.bpm.value + self._bpm_tolerance)
        search_filter = SearchFilter(
            limit=self._max_matches,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
        )
        return tuple(
            await self._track_repository.find_similar(passage.embedding, search_filter)
        )

    # --------------------------------------------------------- exact IDs

    async def _identify_passages(
        self,
        downloaded: DownloadedSet,
        passages: list[Passage],
        *,
        use_shazam: bool,
        use_comments: bool,
        progress: Callable[[AnalyzeEvent], None] | None,
    ) -> list[Passage]:
        """Fill exact-id fields from comments first, then Shazam for the rest."""
        comment_references: tuple[TrackReference, ...] = ()
        if use_comments and self._llm_service is not None and downloaded.comments:
            try:
                comment_references = tuple(
                    await self._llm_service.extract_tracklist_from_comments(
                        downloaded.comments, context=downloaded.title
                    )
                )
            except Exception as exc:  # noqa: BLE001 - LLM failure must not kill analysis
                # An unconfigured or overloaded LLM must never kill an analysis.
                LOGGER.warning("LLM tracklist extraction skipped: %s", exc)

        total_passages = len(passages)
        identified: list[Passage] = []
        failed_count = 0

        for idx, passage in enumerate(passages, start=1):
            identified_passage = self._match_comment_reference(
                passage, comment_references
            )
            msg = ""
            if identified_passage.exact_id_match:
                msg = f"Comments {idx}/{total_passages}: {identified_passage.exact_id_display_name}"
            elif use_shazam and self._fingerprinter is not None:
                if getattr(self._fingerprinter, "is_circuit_open", False):
                    failed_count += 1
                    msg = f"Shazam {idx}/{total_passages}: skipped (circuit open)"
                else:
                    shazam_result = await self._shazam_passage(
                        downloaded, identified_passage
                    )
                    if shazam_result.exact_id_match:
                        identified_passage = shazam_result
                        msg = f"Shazam {idx}/{total_passages}: matched {identified_passage.exact_id_display_name}"
                    else:
                        failed_count += 1
                        msg = f"Shazam {idx}/{total_passages}: no match / timed out"
            else:
                msg = f"Passage {idx}/{total_passages}: unidentified"

            identified.append(identified_passage)
            self._notify(
                progress,
                "identify",
                idx,
                total_passages,
                message=msg,
                failed=failed_count,
            )

        return identified

    def _match_comment_reference(
        self, passage: Passage, references: Sequence[TrackReference]
    ) -> Passage:
        """Attach the best comment reference within ±45 s of the passage."""
        middle = (
            passage.time_range.start_seconds + passage.time_range.duration_seconds / 2.0
        )
        best: TrackReference | None = None
        for reference in references:
            start = (
                reference.timestamp.start_seconds
                if reference.timestamp is not None
                else None
            )
            if start is None:
                continue
            if abs(start - middle) > self._id_tolerance:
                continue
            if best is None or reference.confidence > best.confidence:
                best = reference
        if best is None:
            return passage
        return replace(
            passage,
            exact_id_match=True,
            exact_id_title=best.title,
            exact_id_artist=best.artist,
            exact_id_source="comments",
        )

    async def _shazam_passage(
        self, downloaded: DownloadedSet, passage: Passage
    ) -> Passage:
        assert self._fingerprinter is not None
        span = passage.time_range.duration_seconds
        middle = passage.time_range.start_seconds + span / 2.0
        window = min(self._snippet_seconds, span)
        try:
            snippet = await self._audio_decoder.decode_segment(
                downloaded.audio_path,
                TimeRange(middle - window / 2.0, middle + window / 2.0),
                sample_rate=16_000,
                channels=1,
            )
            reference = await self._fingerprinter.identify_async(snippet)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - fingerprinting is best-effort
            LOGGER.warning(
                "Shazam identification failed for %s: %s", passage.time_range, exc
            )
            return passage
        if reference is None:
            return passage
        return replace(
            passage,
            exact_id_match=True,
            exact_id_title=reference.title,
            exact_id_artist=reference.artist,
            exact_id_source="shazam",
        )

    # ------------------------------------------------------------- persist

    def _build_set(
        self,
        source: str,
        downloaded: DownloadedSet,
        passages: Sequence[Passage],
    ) -> DJSet:
        duration = downloaded.duration_seconds
        clamped_passages: list[Passage] = []
        for p in passages:
            if duration is not None and p.time_range.end_seconds > duration:
                start = min(p.time_range.start_seconds, max(0.0, duration - 0.001))
                clamped_passages.append(
                    replace(p, time_range=TimeRange(start, duration))
                )
            else:
                clamped_passages.append(p)

        bpms = [p.bpm.value for p in clamped_passages if p.bpm is not None]
        embedding = _mean_embedding([p.embedding for p in clamped_passages])
        return DJSet(
            id=f"set-{hashlib.sha256(source.encode('utf-8')).hexdigest()[:12]}",
            title=downloaded.title,
            source_url=downloaded.source_url,
            duration_seconds=downloaded.duration_seconds,
            artist=downloaded.artist,
            thumbnail_url=downloaded.thumbnail_url,
            bpm_min=BPM(min(bpms)) if bpms else None,
            bpm_max=BPM(max(bpms)) if bpms else None,
            embedding=embedding,
            passages=tuple(clamped_passages),
        )

    async def _snowball(
        self, passages: Sequence[Passage], downloaded: DownloadedSet
    ) -> None:
        """Auto-enqueue newly discovered artist names as high-priority seeds."""
        names: dict[str, str] = {}
        for passage in passages:
            if passage.exact_id_artist:
                names[passage.exact_id_artist.casefold()] = passage.exact_id_artist
        if not names:
            return
        seeds = [
            SeedArtist(
                name=name,
                priority_score=DISCOVERY_PRIORITY,
                category="electronic",
                status="pending",
                source="dj-set",
            )
            for name in sorted(names.values())
        ]
        try:
            await self._seed_repository.record_discovery(seeds)
        except Exception:
            LOGGER.exception("seed snowballing failed; analysis result is kept")

    @staticmethod
    def _notify(
        progress: Callable[[AnalyzeEvent], None] | None,
        stage: str,
        completed: int,
        total: int,
        message: str = "",
        failed: int = 0,
    ) -> None:
        if progress is not None:
            progress(
                AnalyzeEvent(
                    stage=stage,
                    completed=completed,
                    total=total,
                    message=message,
                    failed=failed,
                )
            )


# ------------------------------------------------------------------ helpers


def _coerce_features(feature: Any) -> AudioFeatures:
    """Pass through AudioFeatures; failed extractions degrade to empty."""
    if feature is None or isinstance(feature, BaseException):
        return AudioFeatures()
    return feature


def _range_label(passage_range: TimeRange) -> str:
    minutes = int(passage_range.start_seconds // 60)
    seconds = int(passage_range.start_seconds % 60)
    return f"{minutes:02d}:{seconds:02d}"


def _mean_embedding(
    vectors: Sequence[EmbeddingVector | None],
) -> EmbeddingVector | None:
    """L2-normalized mean of the given vectors (None when there are none)."""
    present = [vector for vector in vectors if vector is not None]
    if not present:
        return None
    dimension = len(present[0].values)
    mean = [0.0] * dimension
    for vector in present:
        if len(vector.values) != dimension:
            raise ValueError("passage embeddings have mixed dimensions")
        for index, value in enumerate(vector.values):
            mean[index] += value
    count = float(len(present))
    norm = math.sqrt(math.fsum(value * value / (count * count) for value in mean))
    if norm <= 0.0:
        return None
    normalized = tuple(value / count / norm for value in mean)
    return EmbeddingVector(values=normalized, dimension=dimension)


def _delete_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        LOGGER.warning("could not delete temporary set audio %s", path)


__all__ = ["MAX_EMBED_BATCH", "AnalyzeDJSet", "AnalyzeEvent"]
