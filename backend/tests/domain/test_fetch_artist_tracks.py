"""Tests for the FetchArtistTracks use case against interface doubles."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from domain.entities.track import BlacklistEntry, SeedArtist, Track
from domain.interfaces.catalog import ICatalogProvider, ISeedDiscovery
from domain.interfaces.repositories import (
    IBlacklistRepository,
    ISeedRepository,
    ITrackRepository,
)
from domain.use_cases import (
    FetchArtistProgress,
    FetchArtistTracks,
    IndexProgress,
    IndexResult,
)


class FakeCatalogProvider(ICatalogProvider):
    def __init__(
        self, tracks_by_artist: dict[str, Sequence[Track]] | None = None
    ) -> None:
        self.tracks_by_artist = tracks_by_artist or {}
        self.calls: list[tuple[str, int]] = []

    @property
    def provider_id(self) -> str:
        return "itunes"

    async def search_tracks(self, query: str, *, limit: int = 25) -> Sequence[Track]:
        return ()

    async def lookup_track(self, provider_track_id: str) -> Track | None:
        return None

    async def list_artist_tracks(
        self, artist_name: str, *, limit: int = 50
    ) -> Sequence[Track]:
        self.calls.append((artist_name, limit))
        return self.tracks_by_artist.get(artist_name, ())[:limit]

    async def fetch_preview(self, track: Track) -> bytes | None:
        return None


class FakeTrackRepository(ITrackRepository):
    def __init__(self) -> None:
        self.tracks: dict[str, Track] = {}
        self.upsert_calls: list[Sequence[Track]] = []

    async def upsert_many(self, tracks: Sequence[Track]) -> int:
        self.upsert_calls.append(tuple(tracks))
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
        self, limit: int = 100, max_failures: int = 3
    ) -> Sequence[Track]:
        return ()

    async def list_reindexable(
        self, limit: int = 100, max_failures: int = 3
    ) -> Sequence[Track]:
        return ()

    async def mark_index_failed(self, track_id: str, reason: str | None = None) -> None:
        pass

    async def list_embedded(
        self, limit: int = 20, *, offset: int = 0
    ) -> Sequence[Track]:
        return ()

    async def reset_embeddings(self) -> int:
        return 0


class FakeSeedRepository(ISeedRepository):
    def __init__(self) -> None:
        self.seeds: dict[str, SeedArtist] = {}
        self.statuses: dict[str, str] = {}

    async def upsert_many(self, seeds: Sequence[SeedArtist]) -> int:
        for s in seeds:
            self.seeds[s.name] = s
        return len(seeds)

    async def record_discovery(
        self, seeds: Sequence[SeedArtist], *, priority_increment: float = 0.05
    ) -> int:
        for s in seeds:
            self.seeds[s.name] = s
        return len(seeds)

    async def get_by_name(self, name: str) -> SeedArtist | None:
        return self.seeds.get(name)

    async def list_by_status(
        self, status: Any, limit: int = 100
    ) -> Sequence[SeedArtist]:
        return [s for s in self.seeds.values() if s.status == status][:limit]

    async def update_status(self, name: str, status: Any) -> None:
        self.statuses[name] = status
        if name in self.seeds:
            self.seeds[name] = self.seeds[name].with_status(status)

    async def count_by_category(self, category: str) -> int:
        return sum(1 for s in self.seeds.values() if s.category == category)

    async def count_by_status(self, status: Any) -> int:
        return sum(1 for s in self.seeds.values() if s.status == status)

    async def count(self) -> int:
        return len(self.seeds)


class FakeBlacklistRepository(IBlacklistRepository):
    def __init__(
        self,
        blocked_artists: set[str] | None = None,
        blocked_tracks: set[str] | None = None,
    ) -> None:
        self.blocked_artists = blocked_artists or set()
        self.blocked_tracks = blocked_tracks or set()
        self.entries: list[BlacklistEntry] = []

    async def add(self, entry: BlacklistEntry) -> BlacklistEntry:
        self.entries.append(entry)
        return entry

    async def remove(self, entry_id: int) -> bool:
        return True

    async def list_all(
        self,
        *,
        kind: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[BlacklistEntry]:
        return ()

    async def count(self, *, kind: str | None = None) -> int:
        return len(self.entries)

    async def is_artist_blocked(self, normalized_artist: str) -> bool:
        from domain._validation import normalize_artist_key

        return normalize_artist_key(normalized_artist) in self.blocked_artists

    async def is_track_blocked(self, artist_name: str, track_title: str) -> bool:
        from domain._validation import normalize_track_key

        return normalize_track_key(artist_name, track_title) in self.blocked_tracks

    async def get_blocked_artist_keys(self) -> frozenset[str]:
        return frozenset(self.blocked_artists)

    async def get_blocked_track_keys(self) -> frozenset[str]:
        return frozenset(self.blocked_tracks)


class FakeSeedDiscovery(ISeedDiscovery):
    def __init__(self, related: Sequence[SeedArtist] = ()) -> None:
        self.related = tuple(related)
        self.calls: list[dict[str, Any]] = []

    async def discover(
        self,
        *,
        electronic_limit: int = 1000,
        general_limit: int = 300,
        max_depth: int = 2,
        progress: Any = None,
        seed_artists: Sequence[str] | None = None,
    ) -> Sequence[SeedArtist]:
        self.calls.append(
            {
                "electronic_limit": electronic_limit,
                "seed_artists": seed_artists,
            }
        )
        return self.related[:electronic_limit]


class FakeIndexCatalog:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def execute(
        self,
        *,
        limit: int = 500,
        track_ids: Sequence[str] | None = None,
        progress: Any = None,
        **kwargs: Any,
    ) -> IndexResult:
        self.calls.append({"limit": limit, "track_ids": track_ids})
        if progress and track_ids:
            progress(IndexProgress(processed=len(track_ids), failed=0))
        return IndexResult(
            processed=len(track_ids or ()),
            failed=0,
            embedded_total=len(track_ids or ()),
        )


@pytest.mark.asyncio
async def test_fetch_artist_tracks_basic() -> None:
    track1 = Track(id="t1", title="Title 1", artist="Enrico", source="itunes")
    track2 = Track(id="t2", title="Title 2", artist="Enrico", source="itunes")
    provider = FakeCatalogProvider({"Enrico": [track1, track2]})
    track_repo = FakeTrackRepository()
    seed_repo = FakeSeedRepository()

    use_case = FetchArtistTracks(
        catalog_provider=provider,
        track_repository=track_repo,
        seed_repository=seed_repo,
    )

    events: list[FetchArtistProgress] = []
    res = await use_case.execute(
        "Enrico",
        tracks_limit=10,
        auto_index=False,
        discover_related=False,
        progress=events.append,
    )

    assert res.artist == "Enrico"
    assert res.tracks_found == 2
    assert res.tracks_saved == 2
    assert res.tracks_indexed == 0
    assert res.related_seeds_found == 0

    assert len(track_repo.tracks) == 2
    assert seed_repo.seeds["Enrico"].status == "fetched"
    assert any(e.stage == "done" for e in events)


@pytest.mark.asyncio
async def test_fetch_artist_blocked_by_blacklist() -> None:
    provider = FakeCatalogProvider()
    track_repo = FakeTrackRepository()
    blacklist_repo = FakeBlacklistRepository(blocked_artists={"bad artist"})

    use_case = FetchArtistTracks(
        catalog_provider=provider,
        track_repository=track_repo,
        blacklist_repository=blacklist_repo,
    )

    with pytest.raises(ValueError, match="is blacklisted"):
        await use_case.execute("Bad Artist")


@pytest.mark.asyncio
async def test_fetch_artist_auto_index_and_related() -> None:
    track1 = Track(id="t1", title="Title 1", artist="Charlotte", source="itunes")
    provider = FakeCatalogProvider({"Charlotte": [track1]})
    track_repo = FakeTrackRepository()
    seed_repo = FakeSeedRepository()
    indexer = FakeIndexCatalog()
    related_seed = SeedArtist(
        name="Amelie Lens",
        priority_score=0.9,
        category="electronic",
        status="pending",
        source="deezer",
    )
    discovery = FakeSeedDiscovery([related_seed])

    use_case = FetchArtistTracks(
        catalog_provider=provider,
        track_repository=track_repo,
        seed_repository=seed_repo,
        seed_discovery=discovery,
        index_catalog=indexer,  # type: ignore[arg-type]
    )

    res = await use_case.execute(
        "Charlotte",
        tracks_limit=5,
        auto_index=True,
        discover_related=True,
        related_limit=3,
    )

    assert res.tracks_found == 1
    assert res.tracks_saved == 1
    assert res.tracks_indexed == 1
    assert res.related_seeds_found == 1

    assert len(indexer.calls) == 1
    assert indexer.calls[0]["track_ids"] == ["t1"]
    assert "Amelie Lens" in seed_repo.seeds


def test_fetch_artist_invalid_args() -> None:
    provider = FakeCatalogProvider()
    track_repo = FakeTrackRepository()
    use_case = FetchArtistTracks(
        catalog_provider=provider,
        track_repository=track_repo,
    )

    with pytest.raises(ValueError, match="empty"):
        import asyncio

        asyncio.run(use_case.execute("   "))

    with pytest.raises(ValueError, match="positive"):
        asyncio.run(use_case.execute("Valid", tracks_limit=0))
