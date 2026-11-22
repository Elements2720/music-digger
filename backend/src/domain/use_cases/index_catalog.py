"""Use case: stream-index catalog previews into embeddings and features.

The pipeline is a bounded producer-consumer flow so a 16 GB RAM machine can
run it indefinitely:

1. **Producers** download each 30 s preview through ``IAudioDecoder`` and
   decode it to mono float32 PCM entirely in RAM. The decoder bounds its own
   download/decode concurrency (semaphore) and the hand-off queue is bounded
   (default ``maxsize=64``), so at most a handful of previews is ever resident.
2. **CPU stage** extracts BPM and Camelot key on a bounded
   ``ProcessPoolExecutor`` (default 4 workers, ceiling 10 for a Ryzen 5 5600X).
3. **GPU stage** embeds full micro-batches (default 16, hard cap 48) with the
   CLAP embedder, then the batch is persisted to SQLite + LanceDB and every
   PCM buffer is released immediately. Previews are never written to disk.

The run is fully resumable: completed batches are persisted before the next
one starts, tracks that fail (dead URL, corrupt stream, decode error) are
marked through ``ITrackRepository.mark_index_failed`` so a single broken link
never stalls the pipeline, and re-running skips already-embedded tracks.
LanceDB's IVF-PQ index creation is triggered automatically by the repository
once the embedded count crosses 10,000 rows.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import dataclass, replace
from typing import Any

from ..entities.track import Track
from ..interfaces.audio_engine import IAudioDecoder, IAudioEmbedder, IFeatureExtractor
from ..interfaces.repositories import ITrackRepository

LOGGER = logging.getLogger(__name__)

_MAX_BATCH_SIZE = 48
_DEFAULT_QUEUE_MAXSIZE = 64
_DEFAULT_CHUNK_SIZE = 32


@dataclass(frozen=True, slots=True)
class IndexProgress:
    """Counters emitted after every persisted batch or failed track."""

    processed: int
    failed: int


@dataclass(frozen=True, slots=True)
class IndexResult:
    """Summary of one indexing run."""

    processed: int
    failed: int
    embedded_total: int


class _RunCounters:
    """Mutable running totals shared by the pipeline stages."""

    __slots__ = ("failed", "processed")

    def __init__(self) -> None:
        self.processed = 0
        self.failed = 0


class IndexCatalog:
    """Index pending tracks: decode → CPU features → GPU embeddings → persist."""

    def __init__(
        self,
        *,
        track_repository: ITrackRepository,
        audio_decoder: IAudioDecoder,
        feature_extractor: IFeatureExtractor,
        audio_embedder: IAudioEmbedder,
        cpu_executor: Executor | None = None,
        cpu_workers: int = 4,
        queue_maxsize: int = _DEFAULT_QUEUE_MAXSIZE,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
    ) -> None:
        if cpu_workers < 1:
            raise ValueError("cpu_workers must be at least 1")
        if queue_maxsize < 1:
            raise ValueError("queue_maxsize must be at least 1")
        if chunk_size < 1:
            raise ValueError("chunk_size must be at least 1")
        self._track_repository = track_repository
        self._audio_decoder = audio_decoder
        self._feature_extractor = feature_extractor
        self._audio_embedder = audio_embedder
        self._cpu_executor = cpu_executor
        self._cpu_workers = cpu_workers
        self._queue_maxsize = queue_maxsize
        self._chunk_size = chunk_size

    async def execute(
        self,
        *,
        limit: int = 500,
        batch_size: int = 16,
        max_failures: int = 3,
        reindex: bool = False,
        track_ids: Sequence[str] | None = None,
        progress: Callable[[IndexProgress], None] | None = None,
    ) -> IndexResult:
        """Index up to ``limit`` tracks in resumable chunks.

        ``batch_size`` is clamped to the embedder's hard cap of 48. With
        ``reindex=True`` already-embedded tracks are selected too, so improved
        ML logic can re-process the whole catalog. When ``track_ids`` is provided,
        only those specific tracks are fetched and indexed. The ``progress`` callback
        is synchronous so CLI progress rendering stays simple; it fires after
        every persisted batch and every failed track.
        """
        if limit < 0:
            raise ValueError("limit must not be negative")
        if max_failures < 0:
            raise ValueError("max_failures must not be negative")
        effective_batch_size = max(1, min(batch_size, _MAX_BATCH_SIZE))

        counters = _RunCounters()
        own_executor = self._cpu_executor is None
        executor = self._cpu_executor or ProcessPoolExecutor(
            max_workers=self._cpu_workers
        )
        producers: list[asyncio.Task[None]] = []

        def notify() -> None:
            if progress is not None:
                progress(
                    IndexProgress(processed=counters.processed, failed=counters.failed)
                )

        try:
            if track_ids is not None:
                fetched = await self._track_repository.get_many(track_ids)
                candidate_tracks = [
                    track
                    for track in fetched
                    if track is not None and (reindex or track.embedding is None)
                ][:limit]

                for i in range(0, len(candidate_tracks), self._chunk_size):
                    chunk = candidate_tracks[i : i + self._chunk_size]
                    queue: asyncio.Queue[tuple[Track, Any, BaseException | None]] = (
                        asyncio.Queue(maxsize=self._queue_maxsize)
                    )
                    producers = [
                        asyncio.create_task(
                            self._produce_track(track, queue), name=f"decode:{track.id}"
                        )
                        for track in chunk
                    ]
                    await self._consume_chunk(
                        queue,
                        expected=len(chunk),
                        batch_size=effective_batch_size,
                        executor=executor,
                        counters=counters,
                        notify=notify,
                    )
                    producers = []
            else:
                remaining = limit
                attempted: set[str] = set()
                while remaining > 0:
                    if reindex:
                        tracks = await self._track_repository.list_reindexable(
                            min(self._chunk_size, remaining),
                            max_failures=max_failures,
                        )
                    else:
                        tracks = await self._track_repository.list_unembedded(
                            min(self._chunk_size, remaining),
                            max_failures=max_failures,
                        )
                    # One attempt per track per run: chunks re-query the
                    # repository, which would otherwise hand failed tracks back
                    # immediately and spin until max_failures is exhausted.
                    tracks = [track for track in tracks if track.id not in attempted]
                    if not tracks:
                        break
                    remaining -= len(tracks)
                    attempted.update(track.id for track in tracks)

                    queue = asyncio.Queue(maxsize=self._queue_maxsize)
                    producers = [
                        asyncio.create_task(
                            self._produce_track(track, queue), name=f"decode:{track.id}"
                        )
                        for track in tracks
                    ]
                    await self._consume_chunk(
                        queue,
                        expected=len(tracks),
                        batch_size=effective_batch_size,
                        executor=executor,
                        counters=counters,
                        notify=notify,
                    )
                    producers = []
        finally:
            for task in producers:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*producers, return_exceptions=True)
            if own_executor:
                executor.shutdown(wait=False, cancel_futures=True)

        return IndexResult(
            processed=counters.processed,
            failed=counters.failed,
            embedded_total=await self._track_repository.count_embedded(),
        )

    async def _produce_track(
        self,
        track: Track,
        queue: asyncio.Queue[tuple[Track, Any, BaseException | None]],
    ) -> None:
        """Download + decode one preview and hand it to the consumer."""
        try:
            if track.preview_url is None:
                raise ValueError("track has no preview URL")
            buffer = await self._audio_decoder.decode_url(
                track.preview_url, sample_rate=48_000, channels=1
            )
        except Exception as exc:  # noqa: BLE001 - one bad link must not stall the run
            LOGGER.warning("Decoding preview for %s failed: %s", track.id, exc)
            await queue.put((track, None, exc))
            return
        await queue.put((track, buffer, None))

    async def _consume_chunk(
        self,
        queue: asyncio.Queue[tuple[Track, Any, BaseException | None]],
        *,
        expected: int,
        batch_size: int,
        executor: Executor,
        counters: _RunCounters,
        notify: Callable[[], None],
    ) -> None:
        """Drain the decode queue, extract features, embed and persist batches."""
        loop = asyncio.get_running_loop()
        pending: list[tuple[Track, Any, Any]] = []  # (track, features, buffer)

        received = 0
        while received < expected:
            track, buffer, error = await queue.get()
            received += 1
            if error is not None:
                await self._track_repository.mark_index_failed(track.id)
                counters.failed += 1
                notify()
                continue
            try:
                features = await loop.run_in_executor(
                    executor, self._feature_extractor.extract, buffer
                )
            except Exception:
                LOGGER.exception("Feature extraction failed for %s", track.id)
                await self._track_repository.mark_index_failed(track.id)
                counters.failed += 1
                notify()
                continue
            pending.append((track, features, buffer))
            if len(pending) >= batch_size:
                await self._flush(pending, counters, notify)

        if pending:
            await self._flush(pending, counters, notify)

    async def _flush(
        self,
        batch: list[tuple[Track, Any, Any]],
        counters: _RunCounters,
        notify: Callable[[], None],
    ) -> None:
        """Embed one bounded batch, persist it, and release the PCM buffers.

        A track is only counted as *indexed* once embedding AND persistence
        succeeded; a failed flush counts every track in the batch as *failed*
        (and marks it so re-runs can distinguish retries from fresh work).
        """
        tracks = [track for track, _, _ in batch]
        try:
            buffers = [buffer for _, _, buffer in batch]
            vectors = await asyncio.to_thread(self._audio_embedder.embed_batch, buffers)
            if len(vectors) != len(tracks):
                raise RuntimeError(
                    f"embedder returned {len(vectors)} vectors "
                    f"for {len(tracks)} buffers"
                )
            hydrated = [
                replace(track, bpm=features.bpm, key=features.key, embedding=vector)
                for (track, features, _), vector in zip(batch, vectors)
            ]
            await self._track_repository.upsert_many(hydrated)
        except Exception:
            LOGGER.exception(
                "Embedding/persistence batch failed; marking %d track(s)",
                len(tracks),
            )
            for track in tracks:
                await self._track_repository.mark_index_failed(track.id)
            counters.failed += len(tracks)
        else:
            counters.processed += len(tracks)
        notify()
        # Release the PCM bytes immediately; nothing is cached to disk.
        batch.clear()


__all__ = ["IndexCatalog", "IndexProgress", "IndexResult"]
