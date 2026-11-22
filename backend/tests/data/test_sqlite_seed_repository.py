"""Tests for the SQLite seed repository."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from data.datasources.local.sqlite_client import SQLiteClient
from data.repositories.seed_repository import SQLiteSeedRepository
from domain.entities.track import SeedArtist


@pytest.fixture
async def sqlite_client(tmp_path) -> AsyncIterator[SQLiteClient]:
    client = SQLiteClient(tmp_path / "app.db")
    await client.connect()
    yield client
    await client.close()


@pytest.fixture
async def repository(sqlite_client) -> SQLiteSeedRepository:
    return SQLiteSeedRepository(sqlite_client)


async def test_schema_enables_wal(sqlite_client: SQLiteClient) -> None:
    row = await sqlite_client.fetchone("PRAGMA journal_mode")
    assert row is not None
    assert str(row["journal_mode"]).lower() == "wal"


async def test_upsert_and_get_by_name_uses_normalized_comparison(
    repository: SQLiteSeedRepository,
) -> None:
    seed = SeedArtist("Miss Monique", 0.8, "electronic", external_id="123")
    assert await repository.upsert_many([seed]) == 1

    found = await repository.get_by_name("  miss  monique ")
    assert found is not None
    assert found.name == "Miss Monique"
    assert found.external_id == "123"
    assert await repository.get_by_name("Unknown DJ") is None


async def test_upsert_keeps_status_and_raises_priority(
    repository: SQLiteSeedRepository,
) -> None:
    await repository.upsert_many(
        [SeedArtist("Solomun", 0.6, "electronic", status="fetched")]
    )
    await repository.upsert_many([SeedArtist("Solomun", 0.9, "electronic")])

    seed = await repository.get_by_name("Solomun")
    assert seed is not None
    assert seed.status == "fetched"
    assert seed.priority_score == 0.9


async def test_upsert_merges_when_deezer_id_collides_with_different_name(
    repository: SQLiteSeedRepository,
) -> None:
    """A second unique index (deezer_id) must merge, not raise."""
    await repository.upsert_many(
        [SeedArtist("Solomun", 0.7, "electronic", external_id="42")]
    )
    await repository.upsert_many(
        [SeedArtist("Solomun (Official)", 0.5, "electronic", external_id="42")]
    )

    merged = await repository.get_by_name("Solomun")
    assert merged is not None
    assert merged.external_id == "42"
    assert merged.priority_score == 0.7
    assert await repository.count() == 1


async def test_record_discovery_increments_priority(
    repository: SQLiteSeedRepository,
) -> None:
    await repository.record_discovery(
        [SeedArtist("Argy", 0.5, "electronic", external_id="1")],
        priority_increment=0.1,
    )
    assert (await repository.get_by_name("Argy")).priority_score == 0.5

    await repository.record_discovery(
        [SeedArtist("Argy", 0.5, "electronic", external_id="1")],
        priority_increment=0.1,
    )
    assert (await repository.get_by_name("Argy")).priority_score == pytest.approx(0.6)
    assert (await repository.get_by_name("Argy")).status == "pending"


async def test_record_discovery_caps_priority_at_one(
    repository: SQLiteSeedRepository,
) -> None:
    seed = SeedArtist("Keinemusik", 0.99, "electronic")
    await repository.record_discovery([seed])
    await repository.record_discovery([seed], priority_increment=0.1)
    assert (await repository.get_by_name("Keinemusik")).priority_score == 1.0


async def test_record_discovery_rejects_invalid_increment(
    repository: SQLiteSeedRepository,
) -> None:
    with pytest.raises(ValueError, match="priority_increment"):
        await repository.record_discovery(
            [SeedArtist("A", 0.5, "electronic")],
            priority_increment=1.5,
        )


async def test_list_by_status_orders_by_priority(
    repository: SQLiteSeedRepository,
) -> None:
    await repository.upsert_many(
        [
            SeedArtist("Low", 0.2, "electronic"),
            SeedArtist("High", 0.9, "electronic"),
            SeedArtist("Mid", 0.5, "general"),
        ]
    )
    pending = await repository.list_by_status("pending", limit=10)
    assert [seed.name for seed in pending] == ["High", "Mid", "Low"]
    assert await repository.list_by_status("pending", limit=2) == pending[:2]
    assert await repository.list_by_status("fetched") == ()


async def test_update_status_marks_fetched(repository: SQLiteSeedRepository) -> None:
    await repository.upsert_many([SeedArtist("Boris Brejcha", 0.7, "electronic")])
    await repository.update_status("boris brejcha", "fetched")
    seed = await repository.get_by_name("Boris Brejcha")
    assert seed is not None
    assert seed.status == "fetched"
    assert await repository.count_by_status("fetched") == 1
    assert await repository.count_by_status("pending") == 0


async def test_update_status_rejects_unknown_status(
    repository: SQLiteSeedRepository,
) -> None:
    with pytest.raises(ValueError, match="status"):
        await repository.update_status("A", "done")


async def test_counts(repository: SQLiteSeedRepository) -> None:
    await repository.upsert_many(
        [
            SeedArtist("A", 0.5, "electronic"),
            SeedArtist("B", 0.5, "electronic"),
            SeedArtist("C", 0.5, "general"),
        ]
    )
    assert await repository.count() == 3
    assert await repository.count_by_category("electronic") == 2
    assert await repository.count_by_category("general") == 1
    assert await repository.count_by_status("pending") == 3
    with pytest.raises(ValueError, match="category"):
        await repository.count_by_category("rock")


async def test_list_by_source(repository: SQLiteSeedRepository) -> None:
    await repository.record_discovery(
        [
            SeedArtist("Artist 1", 1.0, "electronic", source="local-library"),
            SeedArtist("Artist 2", 0.8, "electronic", source="local-library"),
            SeedArtist("Artist 3", 0.5, "electronic", source="deezer"),
        ]
    )
    local_artists = await repository.list_by_source("local-library", limit=10)
    assert len(local_artists) == 2
    assert [a.name for a in local_artists] == ["Artist 1", "Artist 2"]
    assert await repository.list_by_source("nonexistent") == ()


async def test_delete_by_name(repository: SQLiteSeedRepository) -> None:
    await repository.upsert_many(
        [
            SeedArtist("Stephan Bodzin", 0.9, "electronic"),
            SeedArtist("Tale of Us", 0.8, "electronic"),
        ]
    )
    assert await repository.count() == 2
    assert await repository.delete_by_name("stephan bodzin")
    assert await repository.count() == 1
    assert await repository.get_by_name("Stephan Bodzin") is None
    assert not await repository.delete_by_name("Nonexistent Artist")


async def test_blacklist_filters_upsert_and_discovery(
    sqlite_client: SQLiteClient,
) -> None:
    from data.repositories.blacklist_repository import SQLiteBlacklistRepository
    from domain.entities.track import BlacklistEntry

    bl_repo = SQLiteBlacklistRepository(sqlite_client)
    await bl_repo.add(
        BlacklistEntry(
            id=None,
            kind="artist",
            normalized_key="blocked dj",
            display_name="Blocked DJ",
        )
    )

    repo_with_bl = SQLiteSeedRepository(sqlite_client, blacklist=bl_repo)
    written = await repo_with_bl.upsert_many(
        [
            SeedArtist("Blocked DJ", 0.9, "electronic"),
            SeedArtist("Good DJ", 0.8, "electronic"),
        ]
    )
    assert written == 1
    assert await repo_with_bl.get_by_name("Blocked DJ") is None
    assert await repo_with_bl.get_by_name("Good DJ") is not None


async def test_list_seeds_breakdown_and_purge(repository: SQLiteSeedRepository) -> None:
    seeds = [
        SeedArtist("Tale of Us", 0.9, "electronic", status="pending", source="deezer"),
        SeedArtist("ARTBAT", 0.8, "electronic", status="pending", source="itunes"),
        SeedArtist(
            "Solomun", 0.7, "electronic", status="pending", source="local-library"
        ),
        SeedArtist(
            "Boris Brejcha", 0.6, "electronic", status="fetched", source="deezer"
        ),
        SeedArtist("Maceo Plex", 0.5, "electronic", status="fetched", source="deezer"),
        SeedArtist("Stephan Bodzin", 0.4, "general", status="fetched", source="itunes"),
        SeedArtist("Failed Artist", 0.1, "general", status="failed", source="crawl"),
    ]
    await repository.upsert_many(seeds)

    # 1. list_seeds with pagination and ordering
    page1, total = await repository.list_seeds(limit=3, offset=0)
    assert total == 7
    assert len(page1) == 3
    assert page1[0].name == "Tale of Us"
    assert page1[1].name == "ARTBAT"
    assert page1[2].name == "Solomun"

    # 2. list_seeds filter by status
    pending, p_total = await repository.list_seeds(status="pending")
    assert p_total == 3
    assert len(pending) == 3

    # 3. list_seeds filter by source
    local, l_total = await repository.list_seeds(source="local-library")
    assert l_total == 1
    assert local[0].name == "Solomun"

    # 4. list_seeds filter by category
    gen, g_total = await repository.list_seeds(category="general")
    assert g_total == 2
    assert {s.name for s in gen} == {"Stephan Bodzin", "Failed Artist"}

    # 5. list_seeds filter by search query
    searched, s_total = await repository.list_seeds(query="brejcha")
    assert s_total == 1
    assert searched[0].name == "Boris Brejcha"

    # 6. get_breakdown
    breakdown = await repository.get_breakdown()
    assert breakdown.total == 7
    assert breakdown.pending == 3
    assert breakdown.fetched == 3
    assert breakdown.failed == 1
    sources_dict = {s.source: s for s in breakdown.by_source}
    assert "deezer" in sources_dict
    assert sources_dict["deezer"].total == 3
    assert sources_dict["deezer"].pending == 1
    assert sources_dict["deezer"].fetched == 2

    # 7. purge_seeds by status
    purged_failed = await repository.purge_seeds(status="failed")
    assert purged_failed == 1
    assert await repository.get_by_name("Failed Artist") is None
    assert await repository.count() == 6

    # 8. purge_seeds by status and source
    purged_deezer_pending = await repository.purge_seeds(
        status="pending", source="deezer"
    )
    assert purged_deezer_pending == 1
    assert await repository.get_by_name("Tale of Us") is None
    assert await repository.count() == 5
