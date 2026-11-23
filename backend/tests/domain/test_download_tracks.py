"""Tests for the pure domain DownloadTracks use case and related value objects."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest

from domain.entities.track import Track
from domain.interfaces.downloader import ITrackDownloader, TrackDownloadResult
from domain.interfaces.repositories import ITrackRepository
from domain.use_cases.download_tracks import (
    BatchDownloadProgress,
    DownloadTracks,
)
from domain.value_objects.audio_features import EmbeddingVector


@dataclass
class InMemoryTrackRepository(ITrackRepository):
    tracks: dict[str, Track] = field(default_factory=dict)

    async def upsert_many(self, tracks: Sequence[Track]) -> int:
        for t in tracks:
            self.tracks[t.id] = t
        return len(tracks)

    async def get_by_id(self, track_id: str) -> Track | None:
        return self.tracks.get(track_id)

    async def get_by_external_id(self, source: str, external_id: str) -> Track | None:
        return None

    async def get_many(self, track_ids: Sequence[str]) -> Sequence[Track]:
        return [self.tracks[tid] for tid in track_ids if tid in self.tracks]

    async def find_similar(self, embedding: Any, search_filter: Any) -> Any:
        return ()

    async def find_by_filter(self, search_filter: Any) -> Any:
        return ()

    async def search_tracks(self, query: str, limit: int = 30) -> Sequence[Track]:
        return ()

    async def mark_heard(self, track_id: str) -> None:
        pass

    async def set_heard(self, track_id: str, heard: bool) -> None:
        pass

    async def get_heard_ids(self) -> frozenset[str]:
        return frozenset()

    async def count(self) -> int:
        return len(self.tracks)

    async def count_embedded(self) -> int:
        return 0

    async def list_unembedded(
        self, limit: int = 100, *, max_failures: int = 3
    ) -> Sequence[Track]:
        return ()

    async def list_reindexable(
        self, limit: int = 100, *, max_failures: int = 3
    ) -> Sequence[Track]:
        return ()

    async def list_embedded(
        self, limit: int = 20, *, offset: int = 0
    ) -> Sequence[Track]:
        return ()

    async def mark_index_failed(self, track_id: str, reason: str | None = None) -> None:
        pass

    async def reset_embeddings(self) -> int:
        return 0


class FakeDownloader(ITrackDownloader):
    def __init__(self, fail_on_id: str | None = None) -> None:
        self.download_calls: list[str] = []
        self.fail_on_id = fail_on_id

    async def download_track(
        self, track: Track, output_dir: str
    ) -> TrackDownloadResult:
        self.download_calls.append(track.id)
        if self.fail_on_id and track.id == self.fail_on_id:
            raise RuntimeError(f"Simulated network error downloading {track.id}")
        return TrackDownloadResult(
            track_id=track.id,
            file_path=f"{output_dir}/{track.artist} - {track.title}.m4a",
            format="m4a",
        )


def _make_track(
    track_id: str,
    *,
    title: str = "Test Title",
    artist: str = "Test Artist",
    local_path: str | None = None,
) -> Track:
    return Track(
        id=track_id,
        title=title,
        artist=artist,
        bpm=128.0,
        key="8A",
        genre="Techno",
        preview_url="https://audio.test/preview.m4a",
        artwork_url="https://img.test/art.jpg",
        store_url="https://music.apple.com/us/song/123",
        local_path=local_path,
        embedding=EmbeddingVector(values=(0.5, 0.5), dimension=2),
    )


@pytest.mark.asyncio
async def test_download_one_success() -> None:
    track = _make_track("t1")
    repo = InMemoryTrackRepository({"t1": track})
    downloader = FakeDownloader()
    use_case = DownloadTracks(repo, downloader, output_dir="storage/downloads")

    result = await use_case.download_one("t1")
    assert result.track_id == "t1"
    assert result.file_path == "storage/downloads/Test Artist - Test Title.m4a"
    assert result.format == "m4a"

    # Verify track repository updated with local_path, preserving other fields
    updated = await repo.get_by_id("t1")
    assert updated is not None
    assert updated.local_path == result.file_path
    assert updated.bpm is not None and updated.bpm.value == 128.0
    assert updated.key is not None and updated.key.notation == "8A"
    assert updated.embedding is not None


@pytest.mark.asyncio
async def test_download_one_skips_when_already_downloaded_and_not_forced() -> None:
    track = _make_track("t1", local_path="storage/downloads/existing.m4a")
    repo = InMemoryTrackRepository({"t1": track})
    downloader = FakeDownloader()
    use_case = DownloadTracks(repo, downloader, output_dir="storage/downloads")

    result = await use_case.download_one("t1", force=False)
    assert result.file_path == "storage/downloads/existing.m4a"
    assert downloader.download_calls == []


@pytest.mark.asyncio
async def test_download_one_re_downloads_when_forced() -> None:
    track = _make_track("t1", local_path="storage/downloads/existing.m4a")
    repo = InMemoryTrackRepository({"t1": track})
    downloader = FakeDownloader()
    use_case = DownloadTracks(repo, downloader, output_dir="storage/downloads")

    result = await use_case.download_one("t1", force=True)
    assert result.file_path == "storage/downloads/Test Artist - Test Title.m4a"
    assert downloader.download_calls == ["t1"]


@pytest.mark.asyncio
async def test_download_one_raises_on_unknown_track() -> None:
    repo = InMemoryTrackRepository()
    downloader = FakeDownloader()
    use_case = DownloadTracks(repo, downloader, output_dir="storage/downloads")

    with pytest.raises(ValueError, match="Track not found"):
        await use_case.download_one("missing")


@pytest.mark.asyncio
async def test_download_many_batch_with_skips_and_errors() -> None:
    t1 = _make_track("t1")
    t2 = _make_track("t2", local_path="storage/downloads/t2.m4a")
    t3 = _make_track("t3")
    repo = InMemoryTrackRepository({"t1": t1, "t2": t2, "t3": t3})
    downloader = FakeDownloader(fail_on_id="t3")
    use_case = DownloadTracks(repo, downloader, output_dir="storage/downloads")

    progress_events: list[BatchDownloadProgress] = []
    result = await use_case.download_many(
        ["t1", "t2", "t3", "t1"],  # includes duplicate
        skip_existing=True,
        progress=progress_events.append,
    )

    assert result.total == 3
    assert result.downloaded == 1
    assert result.skipped == 1
    assert result.failed == 1
    assert len(result.errors) == 1
    assert "Simulated network error" in result.errors[0]

    # Verify progress events were emitted
    assert len(progress_events) == 3
    assert progress_events[-1].processed == 3
    assert progress_events[-1].failed == 1
