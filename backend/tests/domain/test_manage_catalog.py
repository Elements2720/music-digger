"""Unit tests for the ManageCatalog use case."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

import pytest

from domain.entities.analytics import ArtistSummary
from domain.entities.search import SearchFilter
from domain.entities.track import (
    BlacklistEntry,
    LikedArtist,
    SeedArtist,
    SeedStatus,
    Track,
)
from domain.interfaces.repositories import (
    IBlacklistRepository,
    ILikedArtistRepository,
    ISeedRepository,
    ITrackRepository,
)
from domain.use_cases.manage_catalog import (
    BulkCleanupCriteria,
    ManageCatalog,
)
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

    async def delete_by_artists(
        self, artist_names: Sequence[str]
    ) -> tuple[int, tuple[str, ...]]:
        names_lower = {a.casefold() for a in artist_names}
        matching = [
            tid for tid, t in self.tracks.items() if t.artist.casefold() in names_lower
        ]
        count = await self.delete_by_ids(matching)
        return (count, tuple(matching))

    async def get_artists_with_local_tracks(self) -> frozenset[str]:
        from domain._validation import normalize_artist_key

        return frozenset(
            normalize_artist_key(t.artist)
            for t in self.tracks.values()
            if t.source == "local" or t.local_path is not None
        )

    async def list_by_artist(
        self, artist_name: str, *, limit: int = 200, offset: int = 0
    ) -> Sequence[Track]:
        return tuple(
            t
            for t in self.tracks.values()
            if t.artist.casefold() == artist_name.casefold()
        )[offset : offset + limit]

    async def list_artists_summary(
        self,
        *,
        query: str | None = None,
        genre: str | None = None,
        source: str | None = None,
        min_year: int | None = None,
        sort: str = "tracks_desc",
        limit: int = 50,
        offset: int = 0,
        taste_mode: str = "both",
        liked_artist_keys: frozenset[str] = frozenset(),
        liked_only: bool = False,
    ) -> tuple[Sequence[ArtistSummary], int]:
        from domain._validation import normalize_artist_key

        by_artist: dict[str, list[Track]] = {}
        for t in self.tracks.values():
            by_artist.setdefault(t.artist, []).append(t)

        summaries: list[ArtistSummary] = []
        for artist, trks in by_artist.items():
            norm_k = normalize_artist_key(artist)
            is_liked = norm_k in liked_artist_keys
            if liked_only and not is_liked:
                continue
            if query and query.casefold() not in artist.casefold():
                continue
            if genre and not any(
                t.genre and t.genre.casefold() == genre.casefold() for t in trks
            ):
                continue
            if source and not any(t.source == source for t in trks):
                continue
            genres = tuple({t.genre for t in trks if t.genre})
            sources = tuple({t.source for t in trks if t.source})
            years = [t.release_year for t in trks if t.release_year is not None]
            emb_cnt = sum(1 for t in trks if t.embedding is not None)
            taste_val = getattr(self, "artist_taste_map", {}).get(artist)
            summaries.append(
                ArtistSummary(
                    artist=artist,
                    track_count=len(trks),
                    embedded_count=emb_cnt,
                    genres=genres,
                    sources=sources,
                    sample_track_id=trks[0].id if trks else None,
                    sample_track_title=trks[0].title if trks else None,
                    year_min=min(years) if years else None,
                    year_max=max(years) if years else None,
                    taste_match_percent=taste_val,
                    is_liked=is_liked,
                )
            )
        return tuple(summaries[offset : offset + limit]), len(summaries)

    async def list_artists_summary_by_names(
        self,
        artist_names: Sequence[str],
        *,
        genre: str | None = None,
        source: str | None = None,
        taste_scores: Mapping[str, float | None] | None = None,
        liked_artist_keys: frozenset[str] = frozenset(),
    ) -> tuple[Sequence[ArtistSummary], int]:
        wanted = {name for name in artist_names}
        in_scope, total = await self.list_artists_summary(
            genre=genre,
            source=source,
            taste_mode="both",
            liked_artist_keys=liked_artist_keys,
            limit=100_000,
        )
        matched = []
        for summary in in_scope:
            if summary.artist not in wanted:
                continue
            if taste_scores is not None and summary.artist in taste_scores:
                summary = replace(
                    summary, taste_match_percent=taste_scores[summary.artist]
                )
            matched.append(summary)
        return tuple(matched), total

    async def get_artist_taste_scores(
        self,
        *,
        mode: str = "both",
        liked_artist_keys: frozenset[str] = frozenset(),
    ) -> tuple[dict[str, float], int]:
        scores: dict[str, float] = getattr(self, "artist_taste_map", {})
        return (dict(scores), len(liked_artist_keys))


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

    async def delete_by_names(self, names: Sequence[str]) -> int:
        count = 0
        for n in names:
            if await self.delete_by_name(n):
                count += 1
        return count


class FakeLikedArtistRepository(ILikedArtistRepository):
    def __init__(self, liked_names: Sequence[str] = ()) -> None:
        from domain._validation import normalize_artist_key

        self.liked: dict[str, LikedArtist] = {
            normalize_artist_key(n): LikedArtist(
                artist_name=n,
                normalized_key=normalize_artist_key(n),
                created_at="2026-11-22",
            )
            for n in liked_names
        }

    async def like(self, artist_name: str) -> LikedArtist:
        from domain._validation import normalize_artist_key

        k = normalize_artist_key(artist_name)
        entry = LikedArtist(
            artist_name=artist_name, normalized_key=k, created_at="2026-11-22"
        )
        self.liked[k] = entry
        return entry

    async def unlike(self, artist_name: str) -> bool:
        from domain._validation import normalize_artist_key

        k = normalize_artist_key(artist_name)
        return self.liked.pop(k, None) is not None

    async def is_liked(self, artist_name: str) -> bool:
        from domain._validation import normalize_artist_key

        return normalize_artist_key(artist_name) in self.liked

    async def get_liked_keys(self) -> frozenset[str]:
        return frozenset(self.liked.keys())

    async def list_all(self) -> Sequence[LikedArtist]:
        return tuple(self.liked.values())

    async def count(self) -> int:
        return len(self.liked)


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


@pytest.mark.asyncio
async def test_bulk_delete_artists_basic() -> None:
    t1 = Track(id="t1", title="Trk1", artist="Artist Alpha")
    t2 = Track(id="t2", title="Trk2", artist="Artist Alpha")
    t3 = Track(id="t3", title="Trk3", artist="Artist Beta")
    t4 = Track(id="t4", title="Trk4", artist="Artist Gamma")
    track_repo = FakeTrackRepository([t1, t2, t3, t4])
    seed_repo = FakeSeedRepository()
    await seed_repo.upsert_many(
        [
            SeedArtist("Artist Alpha", 0.8, "electronic"),
            SeedArtist("Artist Beta", 0.6, "electronic"),
            SeedArtist("Artist Gamma", 0.4, "electronic"),
        ]
    )
    blacklist_repo = FakeBlacklistRepository()
    manage = ManageCatalog(
        track_repository=track_repo,
        seed_repository=seed_repo,
        blacklist_repository=blacklist_repo,
    )

    result = await manage.bulk_delete_artists(
        ["Artist Alpha", "Artist Beta"],
        blacklist=True,
        reason="Test purge",
    )

    assert result.artists_requested == 2
    assert result.artists_deleted == 2
    assert result.tracks_deleted == 3
    assert result.seeds_removed == 2
    assert result.blacklisted_count == 2
    assert result.skipped_protected == 0

    # Artist Gamma is untouched
    assert await track_repo.count() == 1
    assert await track_repo.get_by_id("t4") is not None
    assert await seed_repo.count() == 1

    # Blacklist contains the 2 deleted artists
    assert await blacklist_repo.count(kind="artist") == 2


@pytest.mark.asyncio
async def test_bulk_delete_artists_protect_liked_and_local() -> None:
    t_liked = Track(id="t1", title="Liked Track", artist="Liked Guy", source="itunes")
    t_local = Track(
        id="t2",
        title="Local Track",
        artist="Local Hero",
        source="local",
        local_path="C:/music/track.mp3",
    )
    t_other = Track(id="t3", title="Other Track", artist="Delete Me", source="itunes")
    track_repo = FakeTrackRepository([t_liked, t_local, t_other])
    seed_repo = FakeSeedRepository()
    blacklist_repo = FakeBlacklistRepository()
    liked_repo = FakeLikedArtistRepository(["Liked Guy"])

    manage = ManageCatalog(
        track_repository=track_repo,
        seed_repository=seed_repo,
        blacklist_repository=blacklist_repo,
        liked_artist_repository=liked_repo,
    )

    result = await manage.bulk_delete_artists(
        ["Liked Guy", "Local Hero", "Delete Me"],
        blacklist=True,
        protect_liked=True,
        protect_local=True,
    )

    assert result.artists_requested == 3
    assert result.skipped_protected == 2
    assert result.artists_deleted == 1
    assert result.tracks_deleted == 1
    assert result.blacklisted_count == 1

    # Protected artists preserved
    assert await track_repo.get_by_id("t1") is not None
    assert await track_repo.get_by_id("t2") is not None
    assert await track_repo.get_by_id("t3") is None
    # Local audio files on disk are NEVER touched
    local_trk = await track_repo.get_by_id("t2")
    assert local_trk is not None and local_trk.local_path == "C:/music/track.mp3"


def test_bulk_cleanup_criteria_validation() -> None:
    # Empty criteria rejected
    with pytest.raises(ValueError, match="At least one criteria"):
        BulkCleanupCriteria()

    with pytest.raises(ValueError, match="At least one criteria"):
        BulkCleanupCriteria(genre="   ", max_taste_percent=None)

    # Out of range taste rejected
    with pytest.raises(ValueError, match="between 0.0 and 100.0"):
        BulkCleanupCriteria(max_taste_percent=105.0)

    with pytest.raises(ValueError, match="between 0.0 and 100.0"):
        BulkCleanupCriteria(max_taste_percent=-5.0)

    # Invalid taste mode rejected
    with pytest.raises(ValueError, match="Invalid taste_mode"):
        BulkCleanupCriteria(genre="Techno", taste_mode="invalid")  # type: ignore

    # Valid criteria works
    c1 = BulkCleanupCriteria(genre="Ambient")
    assert c1.genre == "Ambient"
    assert c1.max_taste_percent is None

    c2 = BulkCleanupCriteria(max_taste_percent=60.0, protect_liked=False)
    assert c2.max_taste_percent == 60.0
    assert not c2.protect_liked


@pytest.mark.asyncio
async def test_bulk_cleanup_preview_and_execute() -> None:
    t1 = Track(id="t1", title="Trk1", artist="Ambient Guy", genre="Ambient")
    t2 = Track(id="t2", title="Trk2", artist="Pop Star", genre="Pop")
    t3 = Track(id="t3", title="Trk3", artist="Techno Master", genre="Techno")
    t4 = Track(id="t4", title="Trk4", artist="Ambient Good", genre="Ambient")

    track_repo = FakeTrackRepository([t1, t2, t3, t4])
    track_repo.artist_taste_map = {  # type: ignore
        "Ambient Guy": 40.0,
        "Pop Star": 30.0,
        "Techno Master": 85.0,
        "Ambient Good": 75.0,
    }
    seed_repo = FakeSeedRepository()
    blacklist_repo = FakeBlacklistRepository()
    manage = ManageCatalog(
        track_repository=track_repo,
        seed_repository=seed_repo,
        blacklist_repository=blacklist_repo,
    )

    # 1. Preview by genre Ambient -> matches Ambient Guy and Ambient Good
    p_genre = await manage.preview_bulk_cleanup(BulkCleanupCriteria(genre="Ambient"))
    assert p_genre.artist_count == 2
    assert {a.artist for a in p_genre.sample_artists} == {"Ambient Guy", "Ambient Good"}

    # 2. Preview by taste < 50% -> matches Ambient Guy (40%) and Pop Star (30%)
    p_taste = await manage.preview_bulk_cleanup(
        BulkCleanupCriteria(max_taste_percent=50.0)
    )
    assert p_taste.artist_count == 2
    assert {a.artist for a in p_taste.sample_artists} == {"Ambient Guy", "Pop Star"}

    # 3. Preview by BOTH genre Ambient AND taste < 50% -> matches ONLY Ambient Guy
    criteria = BulkCleanupCriteria(genre="Ambient", max_taste_percent=50.0)
    p_both = await manage.preview_bulk_cleanup(criteria)
    assert p_both.artist_count == 1
    assert p_both.track_count == 1
    assert p_both.sample_artists[0].artist == "Ambient Guy"

    # 4. Execute cleanup with the exact same criteria
    res = await manage.execute_bulk_cleanup(criteria, blacklist=True)
    assert res.artists_deleted == p_both.artist_count
    assert res.tracks_deleted == p_both.track_count
    assert res.blacklisted_count == 1

    # Ambient Guy is deleted; others remain
    assert await track_repo.get_by_id("t1") is None
    assert await track_repo.get_by_id("t2") is not None
    assert await track_repo.get_by_id("t3") is not None
    assert await track_repo.get_by_id("t4") is not None


@pytest.mark.asyncio
async def test_bulk_cleanup_reports_skipped_unscored_artists() -> None:
    """Regression: unscored artists were silently dropped from cleanup previews.

    The old resolver filtered them out with no counter, so the wizard showed
    "0 ARTISTS" (or a bare low count) with no explanation. They must now be
    reported through ``skipped_count`` and never matched.
    """
    t1 = Track(id="t1", title="Trk1", artist="Scored Low", genre="Techno")
    t2 = Track(id="t2", title="Trk2", artist="Unscored A", genre="Techno")
    t3 = Track(id="t3", title="Trk3", artist="Unscored B", genre="Techno")
    t4 = Track(id="t4", title="Trk4", artist="Scored High", genre="Techno")

    track_repo = FakeTrackRepository([t1, t2, t3, t4])
    track_repo.artist_taste_map = {  # type: ignore
        "Scored Low": 20.0,
        "Scored High": 90.0,
    }
    manage = ManageCatalog(
        track_repository=track_repo,
        seed_repository=FakeSeedRepository(),
        blacklist_repository=FakeBlacklistRepository(),
    )

    preview = await manage.preview_bulk_cleanup(
        BulkCleanupCriteria(max_taste_percent=40.0)
    )

    # Only the below-threshold artist matches...
    assert preview.artist_count == 1
    assert preview.sample_artists[0].artist == "Scored Low"
    # ...and everything else in scope (2 unscored + 1 above threshold) is reported.
    assert preview.skipped_count == 3

    # A catalog with no taste scores at all matches nothing but explains why.
    empty_repo = FakeTrackRepository([t1, t2, t3, t4])
    manage_empty = ManageCatalog(
        track_repository=empty_repo,
        seed_repository=FakeSeedRepository(),
        blacklist_repository=FakeBlacklistRepository(),
    )
    empty_preview = await manage_empty.preview_bulk_cleanup(
        BulkCleanupCriteria(max_taste_percent=40.0)
    )
    assert empty_preview.artist_count == 0
    assert empty_preview.skipped_count == 4
