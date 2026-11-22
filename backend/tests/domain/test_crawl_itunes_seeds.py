"""Domain use case tests for CrawlITunesSeeds (no I/O, no network)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from domain.entities.track import SeedArtist, Track
from domain.interfaces.catalog import ICatalogProvider
from domain.interfaces.repositories import ISeedRepository
from domain.use_cases.crawl_itunes_seeds import (
    DEFAULT_TECHNO_TERMS,
    CrawlITunesSeeds,
)


def _make_track(track_id: str, *, title: str, artist: str) -> Track:
    return Track(
        id=track_id,
        title=title,
        artist=artist,
        duration_seconds=300.0,
        preview_url="https://preview.test/track.m4a",
        source="itunes",
        external_id=track_id,
    )


class FakeCatalogProvider(ICatalogProvider):
    def __init__(self, tracks_by_keyword: dict[str, Sequence[Track]]) -> None:
        self.tracks_by_keyword = tracks_by_keyword
        self.fail_keywords: set[str] = set()
        self.calls: list[tuple[str, int, bool]] = []

    @property
    def provider_id(self) -> str:
        return "itunes"

    async def crawl_keyword(
        self,
        keyword: str,
        *,
        limit: int = 200,
        expand_compilations: bool = True,
    ) -> Sequence[Track]:
        self.calls.append((keyword, limit, expand_compilations))
        if keyword in self.fail_keywords:
            raise RuntimeError(f"Simulated network error for {keyword}")
        return self.tracks_by_keyword.get(keyword, ())

    async def search_tracks(self, query: str, *, limit: int = 25) -> Sequence[Track]:
        return ()

    async def lookup_track(self, provider_track_id: str) -> Track | None:
        return None

    async def list_artist_tracks(
        self, artist_name: str, *, limit: int = 50
    ) -> Sequence[Track]:
        return ()

    async def fetch_preview(self, track: Track) -> bytes | None:
        return None


@dataclass
class FakeTrackRepository:
    saved: list[Track] = field(default_factory=list)

    async def upsert_many(self, tracks: Sequence[Track]) -> int:
        self.saved.extend(tracks)
        return len(tracks)

    async def get_by_id(self, track_id: str) -> Track | None:
        return next((track for track in self.saved if track.id == track_id), None)


@dataclass
class FakeSeedRepository(ISeedRepository):
    discovered: list[SeedArtist] = field(default_factory=list)

    async def record_discovery(
        self,
        seeds: Sequence[SeedArtist],
        *,
        priority_increment: float = 0.05,
    ) -> int:
        self.discovered.extend(seeds)
        return len(seeds)

    async def upsert_many(self, seeds: Sequence[SeedArtist]) -> int:
        return len(seeds)

    async def get_by_name(self, name: str) -> SeedArtist | None:
        return None

    async def list_by_status(self, status: str, limit: int = 100) -> list[SeedArtist]:
        return []

    async def update_status(self, name: str, status: str) -> None:
        pass

    async def count_by_category(self, category: str) -> int:
        return sum(1 for s in self.discovered if s.category == category)

    async def count_by_status(self, status: str) -> int:
        return sum(1 for s in self.discovered if s.status == status)

    async def count(self) -> int:
        return len(self.discovered)


async def test_crawl_itunes_seeds_progress_and_metrics() -> None:
    t1 = _make_track("1", title="Track 1", artist="Artist A")
    t2 = _make_track("2", title="Track 2", artist="Artist B")
    t3 = _make_track("3", title="Track 3", artist="Artist C")
    provider = FakeCatalogProvider(
        {
            "hypnotic techno": [t1, t2],
            "Drumcode": [t3],
        }
    )
    track_repo = FakeTrackRepository()
    seed_repo = FakeSeedRepository()
    use_case = CrawlITunesSeeds(
        catalog_provider=provider,
        track_repository=track_repo,
        seed_repository=seed_repo,
    )

    events: list[tuple[str, int, int, int]] = []
    result = await use_case.execute(
        terms=["hypnotic techno", "Drumcode"],
        tracks_per_term=50,
        expand_compilations=True,
        save_tracks=True,
        progress=lambda term, idx, total, found: events.append(
            (term, idx, total, found)
        ),
    )

    assert result.terms_processed == 2
    assert result.terms_failed == 0
    assert result.tracks_found == 3
    assert result.tracks_saved == 3
    assert result.artists_discovered == 3
    assert events == [
        ("hypnotic techno", 1, 2, 2),
        ("Drumcode", 2, 2, 1),
    ]
    assert len(track_repo.saved) == 3


async def test_crawl_itunes_seeds_isolates_failed_terms() -> None:
    t1 = _make_track("1", title="Track 1", artist="Artist A")
    provider = FakeCatalogProvider({"good_term": [t1]})
    provider.fail_keywords.add("broken_term")
    track_repo = FakeTrackRepository()
    seed_repo = FakeSeedRepository()
    use_case = CrawlITunesSeeds(
        catalog_provider=provider,
        track_repository=track_repo,
        seed_repository=seed_repo,
    )

    events: list[tuple[str, int, int, int]] = []
    result = await use_case.execute(
        terms=["broken_term", "good_term"],
        progress=lambda term, idx, total, found: events.append(
            (term, idx, total, found)
        ),
    )

    assert result.terms_processed == 1
    assert result.terms_failed == 1
    assert result.tracks_found == 1
    assert result.tracks_saved == 1
    assert result.artists_discovered == 1
    assert events == [
        ("broken_term", 1, 2, 0),
        ("good_term", 2, 2, 1),
    ]


async def test_crawl_itunes_seeds_save_tracks_gate() -> None:
    t1 = _make_track("1", title="Track 1", artist="Artist A")
    provider = FakeCatalogProvider({"drumcode": [t1]})
    track_repo = FakeTrackRepository()
    seed_repo = FakeSeedRepository()
    use_case = CrawlITunesSeeds(
        catalog_provider=provider,
        track_repository=track_repo,
        seed_repository=seed_repo,
    )

    result = await use_case.execute(
        terms=["drumcode"],
        save_tracks=False,
    )

    assert result.tracks_found == 1
    assert result.tracks_saved == 0
    assert len(track_repo.saved) == 0
    assert result.artists_discovered == 1
    assert len(seed_repo.discovered) == 1


async def test_crawl_itunes_seeds_records_correct_seed_artist_payload() -> None:
    t1 = _make_track("1", title="Track 1", artist="Adam Beyer")
    t2 = _make_track("2", title="Track 2", artist="adam beyer")  # duplicate in term
    provider = FakeCatalogProvider({"drumcode": [t1, t2]})
    track_repo = FakeTrackRepository()
    seed_repo = FakeSeedRepository()
    use_case = CrawlITunesSeeds(
        catalog_provider=provider,
        track_repository=track_repo,
        seed_repository=seed_repo,
    )

    result = await use_case.execute(
        terms=["drumcode"],
        priority_score=0.9,
    )

    assert result.artists_discovered == 1
    assert len(seed_repo.discovered) == 1
    seed = seed_repo.discovered[0]
    assert seed.name == "Adam Beyer"
    assert seed.category == "electronic"
    assert seed.source == "itunes-crawl"
    assert seed.priority_score == pytest.approx(0.9)


async def test_crawl_itunes_seeds_validates_inputs() -> None:
    provider = FakeCatalogProvider({})
    use_case = CrawlITunesSeeds(
        catalog_provider=provider,
        track_repository=FakeTrackRepository(),
        seed_repository=FakeSeedRepository(),
    )

    with pytest.raises(ValueError, match="tracks_per_term"):
        await use_case.execute(tracks_per_term=0)
    with pytest.raises(ValueError, match="tracks_per_term"):
        await use_case.execute(tracks_per_term=201)

    with pytest.raises(ValueError, match="priority_score"):
        await use_case.execute(priority_score=-0.1)
    with pytest.raises(ValueError, match="priority_score"):
        await use_case.execute(priority_score=1.1)

    with pytest.raises(ValueError, match="terms must not be empty"):
        await use_case.execute(terms=[])
    with pytest.raises(ValueError, match="terms must contain non-empty strings"):
        await use_case.execute(terms=[""])
    with pytest.raises(ValueError, match="terms must contain non-empty strings"):
        await use_case.execute(terms=["   "])
    with pytest.raises(TypeError, match="terms must be a sequence of strings"):
        await use_case.execute(terms=123)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="each term must be a string"):
        await use_case.execute(terms=["valid", 123])  # type: ignore[list-item]


async def test_crawl_itunes_seeds_uses_default_terms_when_none() -> None:
    provider = FakeCatalogProvider({})
    use_case = CrawlITunesSeeds(
        catalog_provider=provider,
        track_repository=FakeTrackRepository(),
        seed_repository=FakeSeedRepository(),
    )

    result = await use_case.execute(terms=None)
    assert result.terms_processed == len(DEFAULT_TECHNO_TERMS)
    assert len(provider.calls) == len(DEFAULT_TECHNO_TERMS)
    assert provider.calls[0][0] == DEFAULT_TECHNO_TERMS[0]
