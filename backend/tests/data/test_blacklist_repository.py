"""Tests for SQLiteBlacklistRepository."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from data.datasources.local.sqlite_client import SQLiteClient
from data.repositories.blacklist_repository import SQLiteBlacklistRepository
from domain.entities.track import BlacklistEntry


@pytest.fixture
async def sqlite_client(tmp_path: Path) -> AsyncIterator[SQLiteClient]:
    client = SQLiteClient(tmp_path / "test_blacklist.db")
    await client.connect()
    yield client
    await client.close()


@pytest.fixture
async def repository(sqlite_client: SQLiteClient) -> SQLiteBlacklistRepository:
    return SQLiteBlacklistRepository(sqlite_client)


async def test_add_and_get_blocked_keys(repository: SQLiteBlacklistRepository) -> None:
    artist_entry = BlacklistEntry(
        id=None,
        kind="artist",
        normalized_key="bad artist",
        display_name="Bad Artist",
        artist_name="Bad Artist",
        reason="Low quality",
    )
    persisted_artist = await repository.add(artist_entry)
    assert persisted_artist.id is not None
    assert persisted_artist.kind == "artist"
    assert persisted_artist.normalized_key == "bad artist"

    track_entry = BlacklistEntry(
        id=None,
        kind="track",
        normalized_key="bad artist|terrible song",
        display_name="Bad Artist - Terrible Song",
        artist_name="Bad Artist",
        track_title="Terrible Song",
        reason="Skipped always",
    )
    persisted_track = await repository.add(track_entry)
    assert persisted_track.id is not None
    assert persisted_track.kind == "track"

    artist_keys = await repository.get_blocked_artist_keys()
    assert "bad artist" in artist_keys
    assert await repository.is_artist_blocked("bad artist")
    assert not await repository.is_artist_blocked("good artist")

    track_keys = await repository.get_blocked_track_keys()
    assert "bad artist|terrible song" in track_keys
    assert await repository.is_track_blocked("bad artist|terrible song")
    assert not await repository.is_track_blocked("bad artist|other song")


async def test_upsert_on_conflict_updates_display_and_reason(
    repository: SQLiteBlacklistRepository,
) -> None:
    entry1 = BlacklistEntry(
        id=None,
        kind="artist",
        normalized_key="duplicate artist",
        display_name="Duplicate Artist",
        reason="Old reason",
    )
    saved1 = await repository.add(entry1)

    entry2 = BlacklistEntry(
        id=None,
        kind="artist",
        normalized_key="duplicate artist",
        display_name="Duplicate Artist V2",
        reason="Updated reason",
    )
    saved2 = await repository.add(entry2)

    assert saved2.id == saved1.id
    assert saved2.display_name == "Duplicate Artist V2"
    assert saved2.reason == "Updated reason"


async def test_list_all_and_filtering(repository: SQLiteBlacklistRepository) -> None:
    for i in range(5):
        await repository.add(
            BlacklistEntry(
                id=None,
                kind="artist" if i % 2 == 0 else "track",
                normalized_key=f"item {i}",
                display_name=f"Item {i}",
                artist_name=f"Artist {i}",
                track_title=f"Track {i}" if i % 2 != 0 else None,
            )
        )

    assert await repository.count() == 5
    assert await repository.count(kind="artist") == 3
    assert await repository.count(kind="track") == 2

    all_entries = await repository.list_all(limit=10)
    assert len(all_entries) == 5

    artists_only = await repository.list_all(kind="artist")
    assert len(artists_only) == 3
    assert all(e.kind == "artist" for e in artists_only)

    searched = await repository.list_all(query="Item 3")
    assert len(searched) == 1
    assert searched[0].display_name == "Item 3"


async def test_remove_entry_and_cache_invalidation(
    repository: SQLiteBlacklistRepository,
) -> None:
    entry = await repository.add(
        BlacklistEntry(
            id=None,
            kind="artist",
            normalized_key="remove me",
            display_name="Remove Me",
        )
    )
    assert await repository.is_artist_blocked("remove me")

    assert await repository.remove(entry.id)
    assert not await repository.is_artist_blocked("remove me")
    assert await repository.count() == 0
    assert not await repository.remove(999999)


async def test_composite_unique_constraint_allows_same_key_for_artist_and_track(
    repository: SQLiteBlacklistRepository,
) -> None:
    """Ensure an artist and a track can share the same normalized key without colliding."""
    artist_entry = await repository.add(
        BlacklistEntry(
            id=None,
            kind="artist",
            normalized_key="test-key",
            display_name="Test Key Artist",
        )
    )
    track_entry = await repository.add(
        BlacklistEntry(
            id=None,
            kind="track",
            normalized_key="test-key",
            display_name="Test Key Track",
        )
    )
    assert artist_entry.id != track_entry.id
    assert await repository.count() == 2

    # Lookup by kind + normalized_key
    artist_lookup = await repository.get_by_key("artist", "test-key")
    track_lookup = await repository.get_by_key("track", "test-key")
    assert artist_lookup is not None and artist_lookup.kind == "artist"
    assert track_lookup is not None and track_lookup.kind == "track"


async def test_blacklist_integration_blocks_seed_track_and_fetch_metadata(
    sqlite_client: SQLiteClient,
    repository: SQLiteBlacklistRepository,
    tmp_path: Path,
) -> None:
    """Verify blacklisting an artist blocks re-insertion in seeds, tracks, and avoids API calls."""
    from collections.abc import Sequence

    from data.datasources.local.lancedb_client import LanceDBClient
    from data.repositories.seed_repository import SQLiteSeedRepository
    from data.repositories.track_repository import HybridTrackRepository
    from domain._validation import normalize_artist_key
    from domain.entities.track import SeedArtist, Track
    from domain.interfaces.catalog import ICatalogProvider
    from domain.use_cases.fetch_catalog_metadata import FetchCatalogMetadata

    vectors = LanceDBClient(tmp_path / "lancedb_bl_test")
    track_repo = HybridTrackRepository(sqlite_client, vectors, blacklist=repository)
    seed_repo = SQLiteSeedRepository(sqlite_client, blacklist=repository)

    # 1. Blacklist an artist with mixed case, spaces, and punctuation
    raw_artist = "  Adam   Beyer! "
    norm_key = normalize_artist_key(raw_artist)
    assert norm_key == "adam beyer"

    await repository.add(
        BlacklistEntry(
            id=None,
            kind="artist",
            normalized_key=norm_key,
            display_name="Adam Beyer",
            artist_name="Adam Beyer",
            reason="Blocked by taste",
        )
    )

    # 2. Verify SQLiteSeedRepository blocks inserting both lower and mixed-case seeds
    seed_lower = SeedArtist(
        name="adam beyer", priority_score=0.9, category="electronic"
    )
    seed_mixed = SeedArtist(
        name="Adam Beyer", priority_score=0.8, category="electronic"
    )
    inserted_seeds = await seed_repo.upsert_many([seed_lower, seed_mixed])
    assert inserted_seeds == 0
    assert await seed_repo.get_by_name("adam beyer") is None
    assert await seed_repo.get_by_name("Adam Beyer") is None

    # Also record_discovery should block it
    disc_count = await seed_repo.record_discovery([seed_lower])
    assert disc_count == 0

    # 3. Verify HybridTrackRepository blocks inserting tracks by this artist
    track1 = Track(
        id="itunes:ab1",
        title="Your Mind",
        artist="Adam Beyer",
        source="itunes",
    )
    track2 = Track(
        id="itunes:ab2",
        title="Teach Me",
        artist="adam beyer",
        source="itunes",
    )
    valid_track = Track(
        id="itunes:ok1",
        title="Subzero",
        artist="Ben Klock",
        source="itunes",
    )
    inserted_tracks = await track_repo.upsert_many([track1, track2, valid_track])
    assert inserted_tracks == 1  # Only Ben Klock should be inserted
    assert await track_repo.get_by_id("itunes:ab1") is None
    assert await track_repo.get_by_id("itunes:ab2") is None
    assert await track_repo.get_by_id("itunes:ok1") is not None

    # 4. Verify FetchCatalogMetadata skips blacklisted seeds BEFORE provider call
    calls: list[str] = []

    class FakeCatalogProvider(ICatalogProvider):
        @property
        def provider_id(self) -> str:
            return "fake"

        async def search_tracks(
            self, query: str, *, limit: int = 25
        ) -> Sequence[Track]:
            return ()

        async def lookup_track(self, provider_track_id: str) -> Track | None:
            return None

        async def list_artist_tracks(
            self, artist_name: str, *, limit: int = 50
        ) -> Sequence[Track]:
            calls.append(artist_name)
            return ()

        async def fetch_preview(self, track: Track) -> bytes | None:
            return None

        async def crawl_keyword(
            self, keyword: str, *, limit: int = 200, expand_compilations: bool = True
        ) -> Sequence[Track]:
            return ()

    # Insert a seed directly via raw SQL to simulate an existing pre-blacklist seed
    await sqlite_client.execute(
        "INSERT INTO seed_artists (name, name_normalized, priority_score, category, status, source) "
        "VALUES ('Adam Beyer', 'adam beyer', 0.95, 'electronic', 'pending', 'test')"
    )
    await sqlite_client.execute(
        "INSERT INTO seed_artists (name, name_normalized, priority_score, category, status, source) "
        "VALUES ('Ben Klock', 'ben klock', 0.85, 'electronic', 'pending', 'test')"
    )

    fetch_use_case = FetchCatalogMetadata(
        seed_repository=seed_repo,
        catalog_provider=FakeCatalogProvider(),
        track_repository=track_repo,
        blacklist_repository=repository,
    )

    result = await fetch_use_case.execute(artists_limit=10)
    # Adam Beyer was skipped without an API call; Ben Klock was processed
    assert "Adam Beyer" not in calls
    assert "Ben Klock" in calls
    assert result.artists_processed == 1
