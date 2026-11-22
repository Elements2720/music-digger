"""Tests for the Phase 4 DJ set analysis use case (all fakes, no I/O)."""

from __future__ import annotations

import struct
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from domain.entities.dj_set import DJSet, DownloadedSet, SetMatch, TrackMatch
from domain.entities.search import SearchFilter
from domain.entities.track import AudioBuffer, SeedArtist, Track, TrackReference
from domain.use_cases import AnalyzeDJSet, AnalyzeEvent
from domain.value_objects.audio_features import (
    BPM,
    AudioFeatures,
    CamelotKey,
    EmbeddingVector,
    TimeRange,
)

_DIMENSION = 8


def _vector(seed: float) -> EmbeddingVector:
    base = 0.1 + seed * 0.05
    return EmbeddingVector(
        values=tuple(round(base + 0.01 * index, 6) for index in range(_DIMENSION))
    )


@dataclass
class FakeDownloader:
    downloaded: DownloadedSet
    calls: list[tuple[str, Path, bool]] = field(default_factory=list)

    async def fetch_set(
        self, source: str, destination_dir: Path, *, fetch_comments: bool = True
    ) -> DownloadedSet:
        self.calls.append((source, destination_dir, fetch_comments))
        return self.downloaded


@dataclass
class FakeSegmenter:
    ranges: tuple[TimeRange, ...]

    def detect_passages(
        self, path: Path, total_duration_seconds: float
    ) -> Sequence[TimeRange]:
        return self.ranges


@dataclass
class FakeDecoder:
    """Returns a small deterministic buffer tagged by the segment start."""

    buffers: list[AudioBuffer] = field(default_factory=list)

    async def decode_segment(
        self,
        path: Path,
        time_range: TimeRange,
        *,
        sample_rate: int = 48_000,
        channels: int = 1,
    ) -> AudioBuffer:
        del sample_rate, channels
        pcm = struct.pack("<f", time_range.start_seconds) + b"\x00" * 2044
        buffer = AudioBuffer(pcm_bytes=pcm, sample_rate=16_000)
        self.buffers.append(buffer)
        return buffer


@dataclass
class FakeFeatureExtractor:
    """BPM keyed by the decoded core-window start (< 300 s → 128, else 130)."""

    def extract(self, audio: AudioBuffer) -> AudioFeatures:
        start = struct.unpack("<f", audio.pcm_bytes[:4])[0]
        return AudioFeatures(
            bpm=BPM(128.0 if start < 300.0 else 130.0), key=CamelotKey("8A")
        )


@dataclass
class FakeEmbedder:
    def embed_batch(self, audios: Sequence[AudioBuffer]) -> list[EmbeddingVector]:
        vectors: list[EmbeddingVector] = []
        for audio in audios:
            start = struct.unpack("<f", audio.pcm_bytes[:4])[0]
            vectors.append(_vector(start / 600.0))
        return vectors


@dataclass
class FakeTrackRepository:
    filters: list[SearchFilter] = field(default_factory=list)

    async def find_similar(
        self, embedding: EmbeddingVector, search_filter: SearchFilter
    ) -> Sequence[TrackMatch]:
        del embedding
        self.filters.append(search_filter)
        track = Track(id="itunes:9", title="Found", artist="Someone", bpm=BPM(128.0))
        return (TrackMatch(track=track, similarity_score=0.92),)


@dataclass
class FakeSetRepository:
    saved: list[DJSet] = field(default_factory=list)

    async def save(self, dj_set: DJSet) -> None:
        self.saved.append(dj_set)

    async def get_by_id(self, set_id: str) -> DJSet | None:  # pragma: no cover
        return next((item for item in self.saved if item.id == set_id), None)

    async def find_similar_sets(
        self, embedding: EmbeddingVector, *, limit: int = 12
    ) -> Sequence[SetMatch]:  # pragma: no cover
        return ()


@dataclass
class FakeSeedRepository:
    discovered: list[Sequence[SeedArtist]] = field(default_factory=list)

    async def record_discovery(
        self, seeds: Sequence[SeedArtist], *, priority_increment: float = 0.05
    ) -> int:
        del priority_increment
        self.discovered.append(seeds)
        return len(seeds)


@dataclass
class FakeFingerprinter:
    """Identifies only passages whose decoded snippet starts at >= 300 s."""

    async def identify_async(self, audio: AudioBuffer) -> TrackReference | None:
        start = struct.unpack("<f", audio.pcm_bytes[:4])[0]
        if start < 300.0:
            return None
        return TrackReference(artist="ID'd Artist", title="ID'd Track")


@dataclass
class FakeLLM:
    references: Sequence[TrackReference] = ()

    async def extract_tracklist_from_comments(
        self, comments: Sequence[str], *, context: str | None = None
    ) -> Sequence[TrackReference]:
        del comments, context
        return self.references


def _downloaded(tmp_path: Path) -> DownloadedSet:
    audio_path = tmp_path / "cache" / "job.m4a"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"fake")
    return DownloadedSet(
        audio_path=audio_path,
        title="Peak Time Set",
        artist="Test DJ",
        duration_seconds=600.0,
        source_url="https://sound.test/set",
        description="tracklist soon",
        comments=("10:00 Some Artist - Some Track",),
        is_temporary=True,
    )


def _use_case(
    tmp_path: Path,
    downloaded: DownloadedSet,
    *,
    fingerprinter: Any = None,
    llm: Any = None,
    ranges: tuple[TimeRange, ...] = (TimeRange(0.0, 300.0), TimeRange(300.0, 600.0)),
    embed_batch_size: int = 16,
) -> tuple[AnalyzeDJSet, dict[str, Any]]:
    track_repository = FakeTrackRepository()
    set_repository = FakeSetRepository()
    seed_repository = FakeSeedRepository()
    executor = ThreadPoolExecutor(max_workers=2)
    _EXECUTORS.append(executor)
    use_case = AnalyzeDJSet(
        set_downloader=FakeDownloader(downloaded),  # type: ignore[arg-type]
        audio_segmenter=FakeSegmenter(ranges),  # type: ignore[arg-type]
        audio_decoder=FakeDecoder(),  # type: ignore[arg-type]
        feature_extractor=FakeFeatureExtractor(),  # type: ignore[arg-type]
        audio_embedder=FakeEmbedder(),  # type: ignore[arg-type]
        track_repository=track_repository,  # type: ignore[arg-type]
        set_repository=set_repository,  # type: ignore[arg-type]
        seed_repository=seed_repository,  # type: ignore[arg-type]
        fingerprinter=fingerprinter,  # type: ignore[arg-type]
        llm_service=llm,  # type: ignore[arg-type]
        cpu_executor=executor,
        embed_batch_size=embed_batch_size,
    )
    return use_case, {
        "track_repository": track_repository,
        "set_repository": set_repository,
        "seed_repository": seed_repository,
    }


_EXECUTORS: list[ThreadPoolExecutor] = []


@pytest.fixture(autouse=True)
def _shutdown_executors():
    yield
    for executor in _EXECUTORS:
        executor.shutdown(wait=True)
    _EXECUTORS.clear()


async def test_full_pipeline_identifies_and_persists(tmp_path) -> None:
    downloaded = _downloaded(tmp_path)
    llm = FakeLLM(
        references=(
            TrackReference(
                artist="Known Artist",
                title="Known Track",
                timestamp=TimeRange(130.0, 170.0),  # inside passage 1 ±45 s
            ),
        )
    )
    use_case, stores = _use_case(
        tmp_path, downloaded, fingerprinter=FakeFingerprinter(), llm=llm
    )

    events: list[AnalyzeEvent] = []
    dj_set = await use_case.execute(
        "https://sound.test/set",
        destination_dir=tmp_path / "cache",
        progress=events.append,
    )

    # Passage 1 identified from comments, passage 2 from Shazam.
    assert [p.exact_id_source for p in dj_set.passages] == ["comments", "shazam"]
    assert dj_set.passages[0].exact_id_display_name == "Known Artist - Known Track"
    assert dj_set.passages[1].exact_id_display_name == "ID'd Artist - ID'd Track"

    # Set-level aggregates (per-passage BPM 128 / 130 from the fake extractor).
    assert dj_set.bpm_min == BPM(128.0)
    assert dj_set.bpm_max == BPM(130.0)
    assert dj_set.embedding is not None
    norm = sum(value**2 for value in dj_set.embedding.values) ** 0.5
    assert norm == pytest.approx(1.0, abs=1e-6)

    # Every passage got its closest catalog matches.
    assert all(p.closest_matches for p in dj_set.passages)

    # Persisted exactly once, and the downloader forwarded fetch_comments.
    assert len(stores["set_repository"].saved) == 1
    assert stores["set_repository"].saved[0].id == dj_set.id
    assert dj_set.id.startswith("set-")

    # Discovered artist snowballed into the seed list.
    seeds = stores["seed_repository"].discovered
    assert seeds and {seed.name for seed in seeds[0]} == {"Known Artist", "ID'd Artist"}

    # Progress traversed every pipeline stage.
    stages = [event.stage for event in events]
    assert stages[:3] == ["download", "segment", "extract"]
    assert {"extract", "embed", "match", "identify", "persist"} <= set(stages)

    # The temporary download was cleaned up.
    assert not downloaded.audio_path.exists()


async def test_keep_audio_leaves_the_download_in_place(tmp_path) -> None:
    downloaded = _downloaded(tmp_path)
    use_case, _ = _use_case(tmp_path, downloaded, fingerprinter=FakeFingerprinter())
    await use_case.execute(
        "https://sound.test/set",
        destination_dir=tmp_path / "cache",
        keep_audio=True,
    )
    assert downloaded.audio_path.exists()
    downloaded.audio_path.unlink(missing_ok=True)


async def test_missing_duration_aborts_but_cleans_up(tmp_path) -> None:
    downloaded = _downloaded(tmp_path)
    broken = DownloadedSet(
        audio_path=downloaded.audio_path,
        title="No Duration",
        is_temporary=True,
    )
    use_case, _ = _use_case(tmp_path, broken)
    with pytest.raises(ValueError, match="duration"):
        await use_case.execute(
            "https://sound.test/set", destination_dir=tmp_path / "cache"
        )
    assert not broken.audio_path.exists()


async def test_bpm_tolerance_narrows_the_catalog_search(tmp_path) -> None:
    downloaded = _downloaded(tmp_path)
    use_case, stores = _use_case(
        tmp_path, downloaded, fingerprinter=FakeFingerprinter()
    )
    await use_case.execute("https://sound.test/set", destination_dir=tmp_path / "cache")
    bounds = [(f.bpm_min, f.bpm_max) for f in stores["track_repository"].filters]
    assert (123.0, 133.0) in bounds  # passage 1: 128 ± 5
    assert (125.0, 135.0) in bounds  # passage 2: 130 ± 5


async def test_llm_failure_degrades_to_shazam(tmp_path) -> None:
    downloaded = _downloaded(tmp_path)

    class ExplodingLLM:
        async def extract_tracklist_from_comments(
            self, comments: Sequence[str], *, context: str | None = None
        ) -> Sequence[TrackReference]:
            raise RuntimeError("LLM offline")

    use_case, _ = _use_case(
        tmp_path, downloaded, fingerprinter=FakeFingerprinter(), llm=ExplodingLLM()
    )
    dj_set = await use_case.execute(
        "https://sound.test/set", destination_dir=tmp_path / "cache"
    )
    # Passage 1 is out of Shazam's fake reach and the LLM failed, so it stays
    # unidentified; passage 2 is still fingerprinted.
    assert [p.exact_id_source for p in dj_set.passages] == [None, "shazam"]


async def test_unidentified_passages_still_get_closest_matches(tmp_path) -> None:
    downloaded = _downloaded(tmp_path)
    use_case, _ = _use_case(tmp_path, downloaded)  # no fingerprinter, no LLM
    dj_set = await use_case.execute(
        "https://sound.test/set", destination_dir=tmp_path / "cache"
    )
    assert all(not p.exact_id_match for p in dj_set.passages)
    assert all(p.closest_matches for p in dj_set.passages)


async def test_embed_batch_size_cap_is_enforced(tmp_path) -> None:
    downloaded = _downloaded(tmp_path)
    with pytest.raises(ValueError, match="embed_batch_size"):
        _use_case(tmp_path, downloaded, embed_batch_size=33)


async def test_passage_chunking_still_returns_all_passages(tmp_path) -> None:
    downloaded = _downloaded(tmp_path)
    use_case, _ = _use_case(
        tmp_path, downloaded, fingerprinter=FakeFingerprinter(), embed_batch_size=1
    )
    dj_set = await use_case.execute(
        "https://sound.test/set", destination_dir=tmp_path / "cache"
    )
    assert len(dj_set.passages) == 2
    assert dj_set.passages[0].embedding is not None
    assert dj_set.passages[1].embedding is not None


async def test_incremental_per_passage_progress_emits_1_to_n(tmp_path) -> None:
    downloaded = _downloaded(tmp_path)
    ranges = (
        TimeRange(0.0, 200.0),
        TimeRange(200.0, 400.0),
        TimeRange(400.0, 600.0),
    )
    use_case, _ = _use_case(
        tmp_path,
        downloaded,
        ranges=ranges,
        fingerprinter=FakeFingerprinter(),
    )

    events: list[AnalyzeEvent] = []
    await use_case.execute(
        "https://sound.test/set",
        destination_dir=tmp_path / "cache",
        progress=events.append,
    )

    for stage in ("extract", "embed", "match", "identify"):
        stage_events = [e for e in events if e.stage == stage]
        assert len(stage_events) == 3, f"stage {stage} should emit for every passage"
        assert [e.completed for e in stage_events] == [1, 2, 3]
        assert all(e.total == 3 for e in stage_events)
        assert all(e.message for e in stage_events)


async def test_unchecking_shazam_runs_purely_local_and_fast(tmp_path) -> None:
    downloaded = _downloaded(tmp_path)

    class TrackingFingerprinter:
        called = False

        async def identify_async(self, audio: AudioBuffer) -> TrackReference | None:
            self.called = True
            return None

    fingerprinter = TrackingFingerprinter()
    use_case, _ = _use_case(tmp_path, downloaded, fingerprinter=fingerprinter)

    events: list[AnalyzeEvent] = []
    dj_set = await use_case.execute(
        "https://sound.test/set",
        destination_dir=tmp_path / "cache",
        use_shazam=False,
        progress=events.append,
    )

    assert not fingerprinter.called, "Shazam must not be called when use_shazam=False"
    identify_events = [e for e in events if e.stage == "identify"]
    assert len(identify_events) == len(dj_set.passages)
    assert all(not p.exact_id_match for p in dj_set.passages)


async def test_shazam_failure_increments_failed_count_in_progress(tmp_path) -> None:
    downloaded = _downloaded(tmp_path)

    class FailingFingerprinter:
        async def identify_async(self, audio: AudioBuffer) -> TrackReference | None:
            return None

    use_case, _ = _use_case(tmp_path, downloaded, fingerprinter=FailingFingerprinter())

    events: list[AnalyzeEvent] = []
    await use_case.execute(
        "https://sound.test/set",
        destination_dir=tmp_path / "cache",
        use_comments=False,
        use_shazam=True,
        progress=events.append,
    )

    identify_events = [e for e in events if e.stage == "identify"]
    assert len(identify_events) == 2
    assert identify_events[0].failed == 1
    assert identify_events[1].failed == 2
    assert "no match / timed out" in identify_events[0].message


async def test_analyze_dj_set_resets_circuit_breaker_on_execute(tmp_path) -> None:
    downloaded = _downloaded(tmp_path)

    class BreakerFingerprinter:
        def __init__(self) -> None:
            self.reset_called = False

        def reset_circuit_breaker(self) -> None:
            self.reset_called = True

        async def identify_async(self, audio: AudioBuffer) -> TrackReference | None:
            return None

    fingerprinter = BreakerFingerprinter()
    use_case, _ = _use_case(tmp_path, downloaded, fingerprinter=fingerprinter)

    await use_case.execute(
        "https://sound.test/set",
        destination_dir=tmp_path / "cache",
        use_shazam=False,
    )

    assert fingerprinter.reset_called is True


def test_safe_interior_scaling(tmp_path: Path) -> None:
    downloaded = _downloaded(tmp_path)
    use_case, _ = _use_case(tmp_path, downloaded)

    # >= 90s: shrinks by 25s
    r1 = TimeRange(0.0, 120.0)
    safe1 = use_case._safe_interior(r1)
    assert safe1.start_seconds == 25.0
    assert safe1.end_seconds == 95.0

    # 45s <= span < 90s: shrinks by 10s
    r2 = TimeRange(10.0, 70.0)
    safe2 = use_case._safe_interior(r2)
    assert safe2.start_seconds == 20.0
    assert safe2.end_seconds == 60.0

    # < 45s: unchanged
    r3 = TimeRange(0.0, 30.0)
    safe3 = use_case._safe_interior(r3)
    assert safe3.start_seconds == 0.0
    assert safe3.end_seconds == 30.0


def test_merge_duplicate_passages(tmp_path: Path) -> None:
    from domain.entities.dj_set import Passage

    downloaded = _downloaded(tmp_path)
    use_case, _ = _use_case(tmp_path, downloaded)

    p1 = Passage(
        time_range=TimeRange(0.0, 120.0),
        exact_id_match=True,
        exact_id_title="Song A",
        exact_id_artist="Artist 1",
        exact_id_source="shazam",
    )
    p2 = Passage(
        time_range=TimeRange(120.0, 240.0),
        exact_id_match=True,
        exact_id_title="Song A",
        exact_id_artist="Artist 1",
        exact_id_source="shazam",
    )
    p3 = Passage(
        time_range=TimeRange(240.0, 360.0),
        exact_id_match=True,
        exact_id_title="Song B",
        exact_id_artist="Artist 2",
        exact_id_source="shazam",
    )

    merged = use_case._merge_duplicate_passages(
        [p1, p2, p3], total_duration_seconds=360.0
    )
    assert len(merged) == 2
    assert merged[0].time_range.start_seconds == 0.0
    assert merged[0].time_range.end_seconds == 240.0
    assert merged[0].exact_id_title == "Song A"
    assert merged[1].time_range.start_seconds == 240.0
    assert merged[1].time_range.end_seconds == 360.0
    assert merged[1].exact_id_title == "Song B"


async def test_multi_probe_shazam_early_exit_and_fallback(tmp_path: Path) -> None:
    downloaded = _downloaded(tmp_path)

    probe_starts: list[float] = []

    class MultiProbeFingerprinter:
        async def identify_async(self, audio: AudioBuffer) -> TrackReference | None:
            start = struct.unpack("<f", audio.pcm_bytes[:4])[0]
            probe_starts.append(start)
            # Center of [0..300s] safe interior [25..275s] is 150s.
            # Fail at center (150s), succeed at probe 2 (30% -> ~100s)
            if start < 120.0:
                return TrackReference(
                    artist="Second Probe Artist", title="Second Probe Title"
                )
            return None

    fingerprinter = MultiProbeFingerprinter()
    use_case, _ = _use_case(
        tmp_path,
        downloaded,
        fingerprinter=fingerprinter,
        ranges=(TimeRange(0.0, 300.0),),
    )

    dj_set = await use_case.execute(
        "https://sound.test/set",
        destination_dir=tmp_path / "cache",
        use_comments=False,
        use_shazam=True,
        shazam_probes=3,
    )

    assert len(dj_set.passages) == 1
    passage = dj_set.passages[0]
    assert passage.exact_id_match is True
    assert passage.exact_id_title == "Second Probe Title"
    # Should have called probe 1 (failed) then probe 2 (succeeded) and exited early without probe 3
    assert len(probe_starts) == 2
