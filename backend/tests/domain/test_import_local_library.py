"""Unit tests for the ImportLocalLibrary use case."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from domain.entities.track import AudioBuffer, SeedArtist, Track
from domain.interfaces.audio_engine import (
    IAudioDecoder,
    IAudioEmbedder,
    IFeatureExtractor,
)
from domain.interfaces.local_library import ILocalLibraryScanner
from domain.interfaces.repositories import ISeedRepository, ITrackRepository
from domain.use_cases.import_local_library import (
    ImportLocalLibrary,
    ImportLocalProgress,
)
from domain.value_objects.audio_features import (
    BPM,
    AudioFeatures,
    CamelotKey,
    EmbeddingVector,
    TimeRange,
)


class FakeScanner(ILocalLibraryScanner):
    def __init__(self, tracks: Sequence[Track] = ()) -> None:
        self.tracks = list(tracks)
        self.scan_called_with: dict[str, Any] = {}

    async def scan(
        self,
        folder_path: Path | str,
        *,
        recursive: bool = True,
        min_duration_seconds: float = 60.0,
        max_duration_seconds: float = 900.0,
    ) -> Sequence[Track]:
        self.scan_called_with = {
            "folder_path": folder_path,
            "recursive": recursive,
            "min_duration_seconds": min_duration_seconds,
            "max_duration_seconds": max_duration_seconds,
        }
        return self.tracks


class FakeDecoder(IAudioDecoder):
    def __init__(self) -> None:
        self.decoded_ranges: list[TimeRange] = []

    async def decode(self, *args: Any, **kwargs: Any) -> AudioBuffer:
        return AudioBuffer(pcm_bytes=b"\x00" * 4800, sample_rate=48000)

    async def decode_url(self, *args: Any, **kwargs: Any) -> AudioBuffer:
        return AudioBuffer(pcm_bytes=b"\x00" * 4800, sample_rate=48000)

    async def decode_segment(
        self,
        path: Path,
        time_range: TimeRange,
        *,
        sample_rate: int = 48000,
        channels: int = 1,
    ) -> AudioBuffer:
        self.decoded_ranges.append(time_range)
        return AudioBuffer(pcm_bytes=b"\x00" * 4800, sample_rate=sample_rate)


class FakeFeatureExtractor(IFeatureExtractor):
    def extract(self, audio: AudioBuffer) -> AudioFeatures:
        return AudioFeatures(
            bpm=BPM(128.0),
            key=CamelotKey("8A"),
        )


class FakeEmbedder(IAudioEmbedder):
    model_id = "fake-clap"
    embedding_dimension = 2

    def embed(self, audio: AudioBuffer) -> EmbeddingVector:
        return EmbeddingVector(values=(0.7, 0.7), dimension=2)

    def embed_batch(self, audios: Sequence[AudioBuffer]) -> Sequence[EmbeddingVector]:
        return [EmbeddingVector(values=(0.7, 0.7), dimension=2) for _ in audios]


class FakeTrackRepo(ITrackRepository):
    def __init__(self, embedded_ids: Sequence[str] = ()) -> None:
        self.saved: list[Track] = []
        self.embedded_ids = set(embedded_ids)

    async def upsert_many(self, tracks: Sequence[Track]) -> int:
        self.saved.extend(tracks)
        return len(tracks)

    async def get_by_id(self, track_id: str) -> Track | None:
        return next((t for t in self.saved if t.id == track_id), None)

    async def get_by_external_id(self, source: str, external_id: str) -> Track | None:
        return None

    async def get_many(self, track_ids: Sequence[str]) -> Sequence[Track]:
        return [t for t in self.saved if t.id in track_ids]

    async def get_embedded_ids(self, track_ids: Sequence[str]) -> frozenset[str]:
        return frozenset(t_id for t_id in track_ids if t_id in self.embedded_ids)

    async def find_similar(self, *args: Any, **kwargs: Any) -> Any:
        return ()

    async def find_by_filter(self, *args: Any, **kwargs: Any) -> Any:
        return ()

    async def search_tracks(self, *args: Any, **kwargs: Any) -> Any:
        return ()

    async def mark_heard(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def set_heard(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def get_heard_ids(self) -> frozenset[str]:
        return frozenset()

    async def count(self) -> int:
        return len(self.saved)

    async def count_embedded(self) -> int:
        return len(self.saved)

    async def list_unembedded(self, *args: Any, **kwargs: Any) -> Any:
        return ()

    async def list_embedded(self, *args: Any, **kwargs: Any) -> Any:
        return ()

    async def mark_index_failed(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def list_reindexable(self, *args: Any, **kwargs: Any) -> Any:
        return ()

    async def reset_embeddings(self) -> int:
        return 0


class FakeSeedRepo(ISeedRepository):
    def __init__(self) -> None:
        self.recorded_discoveries: list[SeedArtist] = []

    async def upsert_many(self, seeds: Sequence[SeedArtist]) -> int:
        return len(seeds)

    async def record_discovery(
        self, seeds: Sequence[SeedArtist], *, priority_increment: float = 0.05
    ) -> int:
        self.recorded_discoveries.extend(seeds)
        return len(seeds)

    async def get_by_name(self, name: str) -> SeedArtist | None:
        return None

    async def list_by_status(self, *args: Any, **kwargs: Any) -> Any:
        return ()

    async def list_by_source(
        self, source: str, limit: int = 100
    ) -> Sequence[SeedArtist]:
        return [s for s in self.recorded_discoveries if s.source == source][:limit]

    async def update_status(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def count_by_category(self, category: str) -> int:
        return len(self.recorded_discoveries)

    async def count_by_status(self, status: str) -> int:
        return len(self.recorded_discoveries)

    async def count(self) -> int:
        return len(self.recorded_discoveries)


@pytest.mark.asyncio
async def test_import_local_library_decodes_middle_window_and_persists() -> None:
    t1 = Track(
        id="local:abc1",
        title="Moon Rocks",
        artist="Enrico Sangiuliano",
        duration_seconds=360.0,
        source="local",
        local_path="/music/moon_rocks.mp3",
    )
    t2 = Track(
        id="local:abc2",
        title="Shortie",
        artist="Tale Of Us",
        duration_seconds=20.0,
        source="local",
        local_path="/music/shortie.mp3",
    )
    scanner = FakeScanner([t1, t2])
    decoder = FakeDecoder()
    features = FakeFeatureExtractor()
    embedder = FakeEmbedder()
    track_repo = FakeTrackRepo()
    seed_repo = FakeSeedRepo()

    progress_events: list[ImportLocalProgress] = []

    use_case = ImportLocalLibrary(
        scanner=scanner,
        audio_decoder=decoder,
        feature_extractor=features,
        audio_embedder=embedder,
        track_repository=track_repo,
        seed_repository=seed_repo,
        cpu_workers=1,
    )

    result = await use_case.execute(
        "/music",
        recursive=True,
        batch_size=2,
        progress=progress_events.append,
    )

    assert result.scanned == 2
    assert result.imported == 2
    assert result.embedded == 2
    assert result.failed == 0
    assert result.artists_seeded >= 2

    # Check representative middle window calculation
    assert len(decoder.decoded_ranges) == 2
    # For t1 (360s): duration * 0.40 = 144.0, duration 30.0
    assert decoder.decoded_ranges[0].start_seconds == 144.0
    assert decoder.decoded_ranges[0].duration_seconds == 30.0
    # For t2 (20s <= 30s): starts at 0.0, duration 20.0
    assert decoder.decoded_ranges[1].start_seconds == 0.0
    assert decoder.decoded_ranges[1].duration_seconds == 20.0

    # Check persistence
    assert len(track_repo.saved) == 2
    saved_t1 = next(t for t in track_repo.saved if t.id == "local:abc1")
    assert saved_t1.bpm is not None and saved_t1.bpm.value == 128.0
    assert saved_t1.key is not None and saved_t1.key.notation == "8A"
    assert saved_t1.embedding is not None

    # Check artist seeding (priority 1.0, electronic, local-library)
    assert len(seed_repo.recorded_discoveries) == 2
    names = {s.name for s in seed_repo.recorded_discoveries}
    assert "Enrico Sangiuliano" in names
    assert "Tale Of Us" in names
    for seed in seed_repo.recorded_discoveries:
        assert seed.priority_score == 1.0
        assert seed.category == "electronic"
        assert seed.source == "local-library"

    # Check progress events
    stages = [e.stage for e in progress_events]
    assert "scanning" in stages
    assert "found" in stages
    assert "indexing" in stages
    assert "completed" in stages


@pytest.mark.asyncio
async def test_import_local_library_skips_already_embedded_unless_reindex() -> None:
    t1 = Track(
        id="local:already1",
        title="Title 1",
        artist="Artist 1",
        duration_seconds=300.0,
        source="local",
        local_path="/music/t1.mp3",
    )
    t2 = Track(
        id="local:new2",
        title="Title 2",
        artist="Artist 2",
        duration_seconds=300.0,
        source="local",
        local_path="/music/t2.mp3",
    )
    scanner = FakeScanner([t1, t2])
    decoder = FakeDecoder()
    track_repo = FakeTrackRepo(embedded_ids=["local:already1"])
    seed_repo = FakeSeedRepo()

    use_case = ImportLocalLibrary(
        scanner=scanner,
        audio_decoder=decoder,
        feature_extractor=FakeFeatureExtractor(),
        audio_embedder=FakeEmbedder(),
        track_repository=track_repo,
        seed_repository=seed_repo,
    )

    # Without reindex: only local:new2 is decoded and persisted
    result = await use_case.execute("/music", reindex=False)
    assert result.scanned == 2
    assert result.imported == 1
    assert len(decoder.decoded_ranges) == 1
    assert track_repo.saved[0].id == "local:new2"

    # With reindex=True: both tracks are decoded and persisted
    decoder.decoded_ranges.clear()
    track_repo.saved.clear()
    result_reindex = await use_case.execute("/music", reindex=True)
    assert result_reindex.scanned == 2
    assert result_reindex.imported == 2
    assert len(decoder.decoded_ranges) == 2


@pytest.mark.asyncio
async def test_import_local_library_custom_artist_parser() -> None:
    t = Track(
        id="local:collab",
        title="Original (Ben Böhmer Remix)",
        artist="Boris Brejcha feat. Solomun",
        duration_seconds=360.0,
        source="local",
        local_path="/music/track.mp3",
    )
    scanner = FakeScanner([t])
    decoder = FakeDecoder()
    track_repo = FakeTrackRepo()
    seed_repo = FakeSeedRepo()

    # Custom collaborator parser returning multiple artists
    def mock_parser(artist: str, title: str) -> tuple[str, ...]:
        return ("Ben Böhmer", "Boris Brejcha", "Solomun")

    use_case = ImportLocalLibrary(
        scanner=scanner,
        audio_decoder=decoder,
        feature_extractor=FakeFeatureExtractor(),
        audio_embedder=FakeEmbedder(),
        track_repository=track_repo,
        seed_repository=seed_repo,
        artist_parser=mock_parser,
    )

    result = await use_case.execute("/music", seed_artists=True)
    assert result.artists_seeded == 3
    seeded = {s.name for s in seed_repo.recorded_discoveries}
    assert seeded == {"Ben Böhmer", "Boris Brejcha", "Solomun"}
