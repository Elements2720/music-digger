"""Tests for SQLitePlannedSetRepository."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from data.datasources.local.sqlite_client import SQLiteClient
from data.repositories.planned_set_repository import SQLitePlannedSetRepository
from domain.entities.set_plan import PlannedSet


@pytest.fixture
async def sqlite_client(tmp_path) -> AsyncIterator[SQLiteClient]:
    client = SQLiteClient(tmp_path / "app.db")
    await client.connect()
    yield client
    await client.close()


@pytest.fixture
async def repo(sqlite_client: SQLiteClient) -> SQLitePlannedSetRepository:
    return SQLitePlannedSetRepository(sqlite_client)


async def test_save_new_and_get_by_id(repo: SQLitePlannedSetRepository) -> None:
    pset = PlannedSet(id=None, name="Opening Set", track_ids=("t1", "t2", "t3"))
    saved = await repo.save(pset)

    assert saved.id is not None
    assert saved.name == "Opening Set"
    assert saved.track_ids == ("t1", "t2", "t3")
    assert saved.created_at is not None

    fetched = await repo.get_by_id(saved.id)
    assert fetched is not None
    assert fetched.id == saved.id
    assert fetched.name == "Opening Set"
    assert fetched.track_ids == ("t1", "t2", "t3")


async def test_update_planned_set(repo: SQLitePlannedSetRepository) -> None:
    pset = PlannedSet(id=None, name="V1", track_ids=("t1", "t2"))
    saved = await repo.save(pset)
    assert saved.id is not None

    # Update name and reorder/add tracks
    updated = await repo.save(
        PlannedSet(id=saved.id, name="V2 Final", track_ids=("t2", "t1", "t3"))
    )
    assert updated.id == saved.id
    assert updated.name == "V2 Final"
    assert updated.track_ids == ("t2", "t1", "t3")

    fetched = await repo.get_by_id(saved.id)
    assert fetched is not None
    assert fetched.name == "V2 Final"
    assert fetched.track_ids == ("t2", "t1", "t3")


async def test_list_all_and_delete(repo: SQLitePlannedSetRepository) -> None:
    assert await repo.list_all() == ()

    s1 = await repo.save(PlannedSet(id=None, name="Set A", track_ids=("t1",)))
    s2 = await repo.save(PlannedSet(id=None, name="Set B", track_ids=("t2", "t3")))

    all_sets = await repo.list_all()
    assert len(all_sets) == 2
    names = [s.name for s in all_sets]
    assert "Set A" in names
    assert "Set B" in names

    assert s1.id is not None
    assert s2.id is not None

    deleted = await repo.delete(s1.id)
    assert deleted is True

    remaining = await repo.list_all()
    assert len(remaining) == 1
    assert remaining[0].id == s2.id
