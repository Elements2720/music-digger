"""Tests for the Phase 3 IndexCatalog use case against interface doubles."""

from __future__ import annotations

import asyncio
import concurrent.futures
import itertools
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, BinaryIO

import pytest

from domain.entities.search import SearchFilter
from domain.entities.track import AudioBuffer, Track
from domain.interfaces.audio_engine import (
    IAudioDecoder,
    IAudioEmbedder,
    IFeatureExtractor,
)
from domain.interfaces.repositories import ITrackRepository
from domain.use_cases import IndexCatalog, IndexProgress
from domain.value_objects.audio_features import (
    BPM,
    AudioFeatures,
    CamelotKey,
    EmbeddingVector,
)


class InlineExecutor(concurrent.futures.Executor):
    """Runs submitted work immediately on the calling thread (no pickling)."""

    def submit(  # type: ignore[override]
        self,
        fn: Any,
        /,
        *args: Any,
        **kwargs: Any,
    ) -> concurrent.futures.Future[Any]:
        future: concurrent.futures.Future[Any] = concurrent.futures.Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001 - mirrors real executor behavior
            future.set_exception(exc)
        return future


class FakeTrackRepository(ITrackRepository):
    """In-memory track store with failure counters."""

    def __init__(self, tracks: Sequence[Track] = ()) -> None:
        self._tracks: dict[str, Track] = {track.id: track for track in tracks}
        self.failures: dict[str, int] = {}
        self.upsert_batches: list[Sequence[Track]] = []

    async def upsert_many(self, tracks: Sequence[Track]) -> int:
        self.upsert_batches.append(tuple(tracks))
        for track in tracks:
            self._tracks[track.id] = track
        return len(tracks)

    async def get_by_id(self, track_id: str) -> Track | None:
        return self._tracks.get(track_id)

    async def get_by_external_id(self, source: str, external_id: str) -> Track | None:
        return next(
            (
                track
                for track in self._tracks.values()
                if track.source == source and track.external_id == external_id
            ),
            None,
        )

    async def get_many(self, track_ids: Sequence[str]) -> Sequence[Track]:
        return [self._tracks[key] for key in track_ids if key in self._tracks]

    async def find_similar(
        self, embedding: EmbeddingVector, search_filter: SearchFilter
    ) -> Sequence[Any]:
        return ()

    async def find_by_filter(self, search_filter: SearchFilter) -> Sequence[Track]:
        return ()

    async def search_tracks(self, query: str, limit: int = 30) -> Sequence[Track]:
        needle = query.strip().casefold()
        if not needle or limit <= 0:
            return ()
        hits = [
            track
            for track in self._tracks.values()
            if needle in track.title.casefold() or needle in track.artist.casefold()
        ]
        return hits[:limit]

    async def mark_heard(self, track_id: str) -> None:
        return None

    async def set_heard(self, track_id: str, heard: bool) -> None:
        return None

    async def get_heard_ids(self) -> frozenset[str]:
        return frozenset()

    async def count(self) -> int:
        return len(self._tracks)

    async def count_embedded(self) -> int:
        return sum(1 for track in self._tracks.values() if track.embedding is not None)

    async def list_unembedded(
        self, limit: int = 100, *, max_failures: int = 3
    ) -> Sequence[Track]:
        selected = [
            track
            for track in self._tracks.values()
            if track.embedding is None
            and track.preview_url is not None
            and self.failures.get(track.id, 0) < max_failures
        ]
        return selected[: max(0, limit)]

    async def list_embedded(
        self, limit: int = 20, *, offset: int = 0
    ) -> Sequence[Track]:
        embedded = [
            track for track in self._tracks.values() if track.embedding is not None
        ]
        return embedded[offset : offset + max(0, limit)]

    async def mark_index_failed(self, track_id: str) -> None:
        self.failures[track_id] = self.failures.get(track_id, 0) + 1

    async def list_reindexable(
        self, limit: int = 100, *, max_failures: int = 3
    ) -> Sequence[Track]:
        selected = [
            track
            for track in self._tracks.values()
            if track.preview_url is not None
            and self.failures.get(track.id, 0) < max_failures
        ]
        return selected[: max(0, limit)]

    async def reset_embeddings(self) -> int:
        cleared = sum(1 for track in self._tracks.values() if track.embedding)
        for track_id, track in self._tracks.items():
            if track.embedding is not None:
                self._tracks[track_id] = replace(track, embedding=None)
            self.failures[track_id] = 0
        return cleared


class FailingUpsertRepository(FakeTrackRepository):
    """Simulates LanceDB/SQLite persistence blowing up on every flush."""

    def __init__(self, tracks: Sequence[Track] = ()) -> None:
        super().__init__(tracks)
        self.marked_failed: list[str] = []

    async def upsert_many(self, tracks: Sequence[Track]) -> int:
        raise RuntimeError("LanceDB write failed")

    async def mark_index_failed(self, track_id: str) -> None:
        self.marked_failed.append(track_id)
        await super().mark_index_failed(track_id)


class FakeDecoder(IAudioDecoder):
    """Returns one buffer per URL; configured URLs raise instead."""

    def __init__(
        self,
        *,
        failures: dict[str, Exception] | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self.failures = failures or {}
        self.delay_seconds = delay_seconds
        self.decoded_urls: list[str] = []

    async def decode(
        self, source: BinaryIO, *, sample_rate: int = 48_000, channels: int = 1
    ) -> AudioBuffer:
        return AudioBuffer(pcm_bytes=b"\x00\x00\x00\x00", sample_rate=sample_rate)

    async def decode_url(
        self, url: str, *, sample_rate: int = 48_000, channels: int = 1
    ) -> AudioBuffer:
        self.decoded_urls.append(url)
        failure = self.failures.get(url)
        if failure is not None:
            raise failure
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        return AudioBuffer(pcm_bytes=bytes(24), sample_rate=sample_rate)

    async def decode_segment(
        self,
        path: Path,
        time_range: Any,
        *,
        sample_rate: int = 48_000,
        channels: int = 1,
    ) -> AudioBuffer:
        raise NotImplementedError


class FakeExtractor(IFeatureExtractor):
    """Deterministic features for every buffer."""

    def __init__(self, *, bpm: float = 126.0, key: str = "8A") -> None:
        self.bpm = bpm
        self.key = key
        self.extracted = 0

    def extract(self, audio: AudioBuffer) -> AudioFeatures:
        self.extracted += 1
        return AudioFeatures(bpm=BPM(self.bpm), key=CamelotKey(self.key))


class FakeEmbedder(IAudioEmbedder):
    """Records batch sizes and returns one fixed vector per input."""

    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    @property
    def model_id(self) -> str:
        return "fake-clap"

    @property
    def embedding_dimension(self) -> int:
        return 2

    def embed(self, audio: AudioBuffer) -> EmbeddingVector:
        return self.embed_batch([audio])[0]

    def embed_batch(self, audios: Sequence[AudioBuffer]) -> Sequence[EmbeddingVector]:
        self.batch_sizes.append(len(audios))
        return [EmbeddingVector(values=(1.0, 0.0), dimension=2) for _ in audios]


def make_track(number: int, *, preview_url: str | None = "") -> Track:
    # An *unset* preview_url (empty default) generates the canonical URL;
    # passing None explicitly creates a track without a preview.
    resolved_url = (
        f"https://example.test/preview-{number}.m4a"
        if preview_url == ""
        else preview_url
    )
    return Track(
        id=f"track-{number}",
        title=f"Title {number}",
        artist=f"Artist {number % 3}",
        preview_url=resolved_url,
        source="itunes",
        external_id=str(number),
    )


async def test_indexes_every_pending_track() -> None:
    repository = FakeTrackRepository([make_track(i) for i in range(5)])
    decoder = FakeDecoder()
    embedder = FakeEmbedder()
    use_case = IndexCatalog(
        track_repository=repository,
        audio_decoder=decoder,
        feature_extractor=FakeExtractor(),
        audio_embedder=embedder,
        cpu_executor=InlineExecutor(),
    )

    result = await use_case.execute(batch_size=2)

    assert result.processed == 5
    assert result.failed == 0
    assert result.embedded_total == 5
    assert len(decoder.decoded_urls) == 5
    # Every track was persisted with features and an embedding attached.
    persisted = [track for batch in repository.upsert_batches for track in batch]
    assert {track.id for track in persisted} == {f"track-{i}" for i in range(5)}
    for track in persisted:
        assert track.embedding is not None
        assert track.bpm == BPM(126.0)
        assert track.key == CamelotKey("8A")


async def test_respects_limit() -> None:
    repository = FakeTrackRepository([make_track(i) for i in range(8)])
    use_case = IndexCatalog(
        track_repository=repository,
        audio_decoder=FakeDecoder(),
        feature_extractor=FakeExtractor(),
        audio_embedder=FakeEmbedder(),
        cpu_executor=InlineExecutor(),
    )

    result = await use_case.execute(limit=3)

    assert result.processed == 3
    assert await repository.count_embedded() == 3


async def test_failed_preview_marks_track_and_continues() -> None:
    tracks = [make_track(i) for i in range(4)]
    decoder = FakeDecoder(
        failures={"https://example.test/preview-1.m4a": RuntimeError("404")}
    )
    repository = FakeTrackRepository(tracks)
    use_case = IndexCatalog(
        track_repository=repository,
        audio_decoder=decoder,
        feature_extractor=FakeExtractor(),
        audio_embedder=FakeEmbedder(),
        cpu_executor=InlineExecutor(),
    )

    result = await use_case.execute()

    assert result.processed == 3
    assert result.failed == 1
    assert repository.failures["track-1"] == 1
    # A re-run skips embedded tracks entirely and never retries the URL.
    again = await use_case.execute(max_failures=1)
    assert again.processed == 0
    assert again.failed == 0
    assert decoder.decoded_urls.count("https://example.test/preview-1.m4a") == 1


async def test_extraction_failure_marks_track_failed() -> None:
    class ExplodingExtractor(IFeatureExtractor):
        def extract(self, audio: AudioBuffer) -> AudioFeatures:
            raise RuntimeError("librosa exploded")

    repository = FakeTrackRepository([make_track(1), make_track(2)])
    use_case = IndexCatalog(
        track_repository=repository,
        audio_decoder=FakeDecoder(),
        feature_extractor=ExplodingExtractor(),
        audio_embedder=FakeEmbedder(),
        cpu_executor=InlineExecutor(),
    )

    result = await use_case.execute()

    assert result.processed == 0
    assert result.failed == 2
    assert repository.failures == {"track-1": 1, "track-2": 1}


async def test_embedder_receives_bounded_batches() -> None:
    repository = FakeTrackRepository([make_track(i) for i in range(7)])
    embedder = FakeEmbedder()
    use_case = IndexCatalog(
        track_repository=repository,
        audio_decoder=FakeDecoder(),
        feature_extractor=FakeExtractor(),
        audio_embedder=embedder,
        cpu_executor=InlineExecutor(),
    )

    await use_case.execute(batch_size=3)

    assert embedder.batch_sizes == [3, 3, 1]


async def test_flush_failure_counts_tracks_as_failed_not_indexed() -> None:
    """Regression: a persisting failure must not report tracks as indexed."""
    repository = FailingUpsertRepository([make_track(i) for i in range(5)])
    embedder = FakeEmbedder()
    use_case = IndexCatalog(
        track_repository=repository,
        audio_decoder=FakeDecoder(),
        feature_extractor=FakeExtractor(),
        audio_embedder=embedder,
        cpu_executor=InlineExecutor(),
    )

    result = await use_case.execute(batch_size=16)

    assert result.processed == 0
    assert result.failed == 5
    assert result.embedded_total == 0
    assert sorted(repository.marked_failed) == [f"track-{i}" for i in range(5)]
    # The embedder still ran (its failure is in persistence, not inference).
    assert embedder.batch_sizes == [5]
    # Every failure is recorded in the repository's failure counters too.
    assert repository.failures == {f"track-{i}": 1 for i in range(5)}


async def test_retry_failed_requeues_earlier_failures() -> None:
    """A huge max_failures must re-select tracks that exhausted their strikes."""
    repository = FakeTrackRepository([make_track(1)])
    repository.failures["track-1"] = 5  # exhausted under the default of 3
    use_case = IndexCatalog(
        track_repository=repository,
        audio_decoder=FakeDecoder(),
        feature_extractor=FakeExtractor(),
        audio_embedder=FakeEmbedder(),
        cpu_executor=InlineExecutor(),
    )

    blocked = await use_case.execute(max_failures=3)
    retried = await use_case.execute(max_failures=10**9)

    assert blocked.processed == 0
    assert retried.processed == 1
    assert await repository.count_embedded() == 1


async def test_reindex_reprocesses_already_embedded_tracks() -> None:
    """`reindex=True` must re-decode embedded tracks (fresh embeddings)."""
    repository = FakeTrackRepository([make_track(1), make_track(2)])
    decoder = FakeDecoder()
    use_case = IndexCatalog(
        track_repository=repository,
        audio_decoder=decoder,
        feature_extractor=FakeExtractor(),
        audio_embedder=FakeEmbedder(),
        cpu_executor=InlineExecutor(),
    )

    first = await use_case.execute()
    again_without_reindex = await use_case.execute()
    again_with_reindex = await use_case.execute(reindex=True)

    assert first.processed == 2
    assert again_without_reindex.processed == 0  # nothing left unembedded
    assert again_with_reindex.processed == 2
    # Both previews were decoded a second time.
    assert decoder.decoded_urls.count("https://example.test/preview-1.m4a") == 2
    assert decoder.decoded_urls.count("https://example.test/preview-2.m4a") == 2


async def test_batch_size_is_clamped_to_hard_cap() -> None:
    repository = FakeTrackRepository([make_track(i) for i in range(5)])
    embedder = FakeEmbedder()
    use_case = IndexCatalog(
        track_repository=repository,
        audio_decoder=FakeDecoder(),
        feature_extractor=FakeExtractor(),
        audio_embedder=embedder,
        cpu_executor=InlineExecutor(),
    )

    await use_case.execute(batch_size=64)

    assert embedder.batch_sizes == [5]


async def test_progress_reports_running_counters() -> None:
    repository = FakeTrackRepository([make_track(i) for i in range(5)])
    decoder = FakeDecoder(failures={"https://example.test/preview-0.m4a": OSError("x")})
    events: list[IndexProgress] = []
    use_case = IndexCatalog(
        track_repository=repository,
        audio_decoder=decoder,
        feature_extractor=FakeExtractor(),
        audio_embedder=FakeEmbedder(),
        cpu_executor=InlineExecutor(),
    )

    await use_case.execute(batch_size=2, progress=events.append)

    assert events, "progress callback must fire at least once"
    final = events[-1]
    assert final.processed == 4
    assert final.failed == 1
    assert all(
        earlier.processed <= later.processed and earlier.failed <= later.failed
        for earlier, later in itertools.pairwise(events)
    )


async def test_run_is_resumable_across_invocations() -> None:
    repository = FakeTrackRepository([make_track(i) for i in range(6)])
    use_case = IndexCatalog(
        track_repository=repository,
        audio_decoder=FakeDecoder(),
        feature_extractor=FakeExtractor(),
        audio_embedder=FakeEmbedder(),
        cpu_executor=InlineExecutor(),
    )

    first = await use_case.execute(limit=4)
    second = await use_case.execute(limit=4)

    assert first.processed == 4
    assert second.processed == 2
    assert await repository.count_embedded() == 6
    # No track is embedded twice.
    assert repository.failures == {}


async def test_tracks_without_preview_url_are_skipped() -> None:
    repository = FakeTrackRepository([make_track(1), make_track(2, preview_url=None)])
    decoder = FakeDecoder()
    use_case = IndexCatalog(
        track_repository=repository,
        audio_decoder=decoder,
        feature_extractor=FakeExtractor(),
        audio_embedder=FakeEmbedder(),
        cpu_executor=InlineExecutor(),
    )

    result = await use_case.execute()

    assert result.processed == 1
    assert decoder.decoded_urls == ["https://example.test/preview-1.m4a"]


async def test_concurrent_decode_does_not_deadlock_with_backpressure() -> None:
    """A queue smaller than the chunk plus 16 in-flight decodes must complete."""
    repository = FakeTrackRepository([make_track(i) for i in range(40)])
    decoder = FakeDecoder(delay_seconds=0.001)
    use_case = IndexCatalog(
        track_repository=repository,
        audio_decoder=decoder,
        feature_extractor=FakeExtractor(),
        audio_embedder=FakeEmbedder(),
        cpu_executor=InlineExecutor(),
        queue_maxsize=4,
        chunk_size=16,
    )

    result = await use_case.execute(batch_size=8)

    assert result.processed == 40
    assert result.failed == 0


def test_invalid_constructor_arguments_are_rejected() -> None:
    repository = FakeTrackRepository()
    decoder = FakeDecoder()
    extractor = FakeExtractor()
    embedder = FakeEmbedder()
    with pytest.raises(ValueError):
        IndexCatalog(
            track_repository=repository,
            audio_decoder=decoder,
            feature_extractor=extractor,
            audio_embedder=embedder,
            cpu_workers=0,
        )
    with pytest.raises(ValueError):
        IndexCatalog(
            track_repository=repository,
            audio_decoder=decoder,
            feature_extractor=extractor,
            audio_embedder=embedder,
            queue_maxsize=0,
        )
    with pytest.raises(ValueError):
        IndexCatalog(
            track_repository=repository,
            audio_decoder=decoder,
            feature_extractor=extractor,
            audio_embedder=embedder,
            chunk_size=0,
        )
