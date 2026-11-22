"""Unit tests for the ManageCatalog use case."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

import pytest

from domain.entities.search import SearchFilter
from domain.entities.track import BlacklistEntry, SeedArtist, SeedStatus, Track
from domain.interfaces.repositories import (
    IBlacklistRepository,
    ISeedRepository,
    ITrackRepository,
)
from domain.use_cases.manage_catalog import ManageCatalog
from domain.value_objects.audio_features import EmbeddingVector


class FakeTrackRepository(ITrackRepository):
    def __init__(self, tracks: Sequence[Track] = ()) -> None:
        self.tracks: dict[str, Track] = {t.id: t for t in tracks}
        self.deleted_ids: list[str] = []

    async def upsert_many(self, tracks: Sequence[Track]) -> int:
        for t in tracks:
            self.tracks[t.id] = t
        return len(tracks)

    async def get_by_id(self, track_id: str) -> Track | None:
        return self.tracks.get(track_id)

    async def get_by_external_id(self, source: str, external_id: str) -> Track | None:
        for t in self.tracks.values():
            if t.source == source and t.external_id == external_id:
                return t
        return None

    async def get_many(self, track_ids: Sequence[str]) -> Sequence[Track]:
        return tuple(self.tracks[tid] for tid in track_ids if tid in self.tracks)

    async def find_similar(
        self, embedding: EmbeddingVector, search_filter: SearchFilter
    ) -> Sequence:
        return ()

    async def find_by_filter(self, search_filter: SearchFilter) -> Sequence[Track]:
        return tuple(self.tracks.values())

    async def search_tracks(self, query: str, limit: int = 30) -> Sequence[Track]:
        return tuple(self.tracks.values())[:limit]

    async def mark_heard(self, track_id: str) -> None:
        pass

    async def set_heard(self, track_id: str, heard: bool) -> None:
        pass

    async def get_heard_ids(self) -> frozenset[str]:
        return frozenset()

    async def count(self) -> int:
        return len(self.tracks)

    async def count_embedded(self) -> int:
        return sum(1 for t in self.tracks.values() if t.embedding is not None)

    async def list_unembedded(
        self, limit: int = 100, *, max_failures: int = 3
    ) -> Sequence[Track]:
        return ()

    async def list_embedded(
        self, limit: int = 20, *, offset: int = 0
    ) -> Sequence[Track]:
        return ()

    async def mark_index_failed(self, track_id: str) -> None:
        pass

    async def list_reindexable(
        self, limit: int = 100, *, max_failures: int = 3
    ) -> Sequence[Track]:
        return ()

    async def reset_embeddings(self) -> int:
        return 0

    async def delete_by_ids(self, track_ids: Sequence[str]) -> int:
        count = 0
        for tid in track_ids:
            if tid in self.tracks:
                del self.tracks[tid]
                self.deleted_ids.append(tid)
                count += 1
        return count

    async def delete_by_artist(self, artist_name: str) -> tuple[int, tuple[str, ...]]:
        matching = [
            tid
            for tid, t in self.tracks.items()
            if t.artist.casefold() == artist_name.casefold()
        ]
        count = await self.delete_by_ids(matching)
        return (count, tuple(matching))

    async def list_by_artist(
        self, artist_name: str, *, limit: int = 200, offset: int = 0
    ) -> Sequence[Track]:
        return tuple(
            t
            for t in self.tracks.values()
            if t.artist.casefold() == artist_name.casefold()
        )[offset : offset + limit]


class FakeSeedRepository(ISeedRepository):
    def __init__(self) -> None:
        self.seeds: dict[str, SeedArtist] = {}

    async def upsert_many(self, seeds: Sequence[SeedArtist]) -> int:
        for s in seeds:
            self.seeds[s.name.casefold()] = s
        return len(seeds)

    async def record_discovery(
        self, seeds: Sequence[SeedArtist], *, priority_increment: float = 0.05
    ) -> int:
        return await self.upsert_many(seeds)

    async def get_by_name(self, name: str) -> SeedArtist | None:
        return self.seeds.get(name.casefold())

    async def list_by_status(
        self, status: SeedStatus, limit: int = 100
    ) -> Sequence[SeedArtist]:
        return tuple(s for s in self.seeds.values() if s.status == status)[:limit]

    async def update_status(self, name: str, status: SeedStatus) -> None:
        if name.casefold() in self.seeds:
            self.seeds[name.casefold()] = replace(
                self.seeds[name.casefold()], status=status
            )

    async def count_by_category(self, category: str) -> int:
        return sum(1 for s in self.seeds.values() if s.category == category)

    async def count_by_status(self, status: SeedStatus) -> int:
        return sum(1 for s in self.seeds.values() if s.status == status)

    async def count(self) -> int:
        return len(self.seeds)

    async def delete_by_name(self, name: str) -> bool:
        if name.casefold() in self.seeds:
            del self.seeds[name.casefold()]
            return True
        return False


class FakeBlacklistRepository(IBlacklistRepository):
    def __init__(self) -> None:
        self.entries: dict[int, BlacklistEntry] = {}
        self._next_id = 1

    async def add(self, entry: BlacklistEntry) -> BlacklistEntry:
        # Check if already present by normalized_key
        for eid, existing in self.entries.items():
            if existing.normalized_key == entry.normalized_key:
                updated = BlacklistEntry(
                    id=eid,
                    kind=entry.kind,
                    normalized_key=entry.normalized_key,
                    display_name=entry.display_name,
                    artist_name=entry.artist_name,
                    track_title=entry.track_title,
                    reason=entry.reason,
                    created_at="2026-11-22",
                )
                self.entries[eid] = updated
                return updated
        eid = self._next_id
        self._next_id += 1
        persisted = BlacklistEntry(
            id=eid,
            kind=entry.kind,
            normalized_key=entry.normalized_key,
            display_name=entry.display_name,
            artist_name=entry.artist_name,
            track_title=entry.track_title,
            reason=entry.reason,
            created_at="2026-11-22",
        )
        self.entries[eid] = persisted
        return persisted

    async def remove(self, entry_id: int) -> bool:
        if entry_id in self.entries:
            del self.entries[entry_id]
            return True
        return False

    async def list_all(
        self,
        *,
        kind: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[BlacklistEntry]:
        result = list(self.entries.values())
        if kind:
            result = [e for e in result if e.kind == kind]
        if query:
            q = query.casefold()
            result = [e for e in result if q in e.display_name.casefold()]
        return tuple(result[offset : offset + limit])

    async def count(self, *, kind: str | None = None) -> int:
        if kind:
            return sum(1 for e in self.entries.values() if e.kind == kind)
        return len(self.entries)

    async def get_blocked_artist_keys(self) -> frozenset[str]:
        return frozenset(
            e.normalized_key for e in self.entries.values() if e.kind == "artist"
        )

    async def get_blocked_track_keys(self) -> frozenset[str]:
        return frozenset(
            e.normalized_key for e in self.entries.values() if e.kind == "track"
        )

    async def is_artist_blocked(self, normalized_artist: str) -> bool:
        return normalized_artist in await self.get_blocked_artist_keys()

    async def is_track_blocked(self, normalized_track_key: str) -> bool:
        return normalized_track_key in await self.get_blocked_track_keys()


@pytest.fixture
def sample_tracks() -> list[Track]:
    return [
        Track(id="t1", title="Solaris", artist="Artbat"),
        Track(id="t2", title="Return to Oz", artist="Artbat"),
        Track(id="t3", title="Age of Love", artist="Charlotte de Witte"),
    ]


async def test_delete_track_nonexistent(sample_tracks: list[Track]) -> None:
    track_repo = FakeTrackRepository(sample_tracks)
    seed_repo = FakeSeedRepository()
    blacklist_repo = FakeBlacklistRepository()
    manage = ManageCatalog(
        track_repository=track_repo,
        seed_repository=seed_repo,
        blacklist_repository=blacklist_repo,
    )

    result = await manage.delete_track("nonexistent")
    assert not result.deleted
    assert not result.blacklisted
    assert len(track_repo.tracks) == 3


async def test_delete_track_without_blacklist(sample_tracks: list[Track]) -> None:
    track_repo = FakeTrackRepository(sample_tracks)
    seed_repo = FakeSeedRepository()
    blacklist_repo = FakeBlacklistRepository()
    manage = ManageCatalog(
        track_repository=track_repo,
        seed_repository=seed_repo,
        blacklist_repository=blacklist_repo,
    )

    result = await manage.delete_track("t1", blacklist=False)
    assert result.deleted
    assert not result.blacklisted
    assert "t1" not in track_repo.tracks
    assert await blacklist_repo.count() == 0


async def test_delete_track_with_blacklist(sample_tracks: list[Track]) -> None:
    track_repo = FakeTrackRepository(sample_tracks)
    seed_repo = FakeSeedRepository()
    blacklist_repo = FakeBlacklistRepository()
    manage = ManageCatalog(
        track_repository=track_repo,
        seed_repository=seed_repo,
        blacklist_repository=blacklist_repo,
    )

    result = await manage.delete_track("t1", blacklist=True, reason="User disliked")
    assert result.deleted
    assert result.blacklisted
    assert "t1" not in track_repo.tracks
    assert await blacklist_repo.count() == 1
    blocked_keys = await blacklist_repo.get_blocked_track_keys()
    assert "artbat|solaris" in blocked_keys


async def test_delete_artist_with_and_without_blacklist(
    sample_tracks: list[Track],
) -> None:
    track_repo = FakeTrackRepository(sample_tracks)
    seed_repo = FakeSeedRepository()
    await seed_repo.upsert_many(
        [
            SeedArtist(name="Artbat", category="electronic", priority_score=0.9),
            SeedArtist(
                name="Charlotte de Witte", category="electronic", priority_score=0.8
            ),
        ]
    )
    blacklist_repo = FakeBlacklistRepository()
    manage = ManageCatalog(
        track_repository=track_repo,
        seed_repository=seed_repo,
        blacklist_repository=blacklist_repo,
    )

    result = await manage.delete_artist("Artbat", blacklist=True, reason="Irrelevant")
    assert result.tracks_deleted == 2
    assert result.seed_removed
    assert result.blacklisted
    assert "t1" not in track_repo.tracks
    assert "t2" not in track_repo.tracks
    assert "t3" in track_repo.tracks
    assert await seed_repo.get_by_name("Artbat") is None
    assert await seed_repo.get_by_name("Charlotte de Witte") is not None
    assert await blacklist_repo.is_artist_blocked("artbat")


async def test_direct_blacklist_operations() -> None:
    track_repo = FakeTrackRepository()
    seed_repo = FakeSeedRepository()
    blacklist_repo = FakeBlacklistRepository()
    manage = ManageCatalog(
        track_repository=track_repo,
        seed_repository=seed_repo,
        blacklist_repository=blacklist_repo,
    )

    artist_entry = await manage.add_blacklist_artist("Bad Artist", reason="Spam")
    assert artist_entry.id is not None
    assert artist_entry.kind == "artist"
    assert artist_entry.normalized_key == "bad artist"

    track_entry = await manage.add_blacklist_track(
        "Bad Artist", "Annoying Track", reason="Noise"
    )
    assert track_entry.kind == "track"
    assert track_entry.normalized_key == "bad artist|annoying track"

    assert await manage.count_blacklist() == 2
    assert await manage.count_blacklist(kind="artist") == 1
    assert await manage.count_blacklist(kind="track") == 1

    entries = await manage.list_blacklist()
    assert len(entries) == 2

    filtered = await manage.list_blacklist(query="Annoying")
    assert len(filtered) == 1
    assert filtered[0].track_title == "Annoying Track"

    removed = await manage.remove_blacklist_entry(artist_entry.id)
    assert removed
    assert await manage.count_blacklist() == 1
