"""Tests for SQLiteLikedArtistRepository."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from data.datasources.local.sqlite_client import SQLiteClient
from data.repositories.liked_artist_repository import SQLiteLikedArtistRepository


@pytest.fixture
async def sqlite_client(tmp_path) -> AsyncIterator[SQLiteClient]:
    client = SQLiteClient(tmp_path / "app.db")
    await client.connect()
    yield client
    await client.close()


@pytest.fixture
async def repo(sqlite_client: SQLiteClient) -> SQLiteLikedArtistRepository:
    return SQLiteLikedArtistRepository(sqlite_client)


async def test_like_and_is_liked(repo: SQLiteLikedArtistRepository) -> None:
    assert await repo.count() == 0
    assert not await repo.is_liked("Enrico Sangiuliano")

    liked = await repo.like("Enrico Sangiuliano")
    assert liked.artist_name == "Enrico Sangiuliano"
    assert liked.normalized_key == "enrico sangiuliano"
    assert liked.created_at is not None

    assert await repo.count() == 1
    assert await repo.is_liked("Enrico Sangiuliano")
    assert await repo.is_liked("  enrico  sangiuliano  ")


async def test_like_is_idempotent(repo: SQLiteLikedArtistRepository) -> None:
    await repo.like("Adam Beyer")
    assert await repo.count() == 1

    liked2 = await repo.like("Adam Beyer")
    assert liked2.artist_name == "Adam Beyer"
    assert await repo.count() == 1


async def test_unlike_removes_entry(repo: SQLiteLikedArtistRepository) -> None:
    await repo.like("Charlotte de Witte")
    assert await repo.is_liked("Charlotte de Witte")

    removed = await repo.unlike("Charlotte de Witte")
    assert removed is True
    assert not await repo.is_liked("Charlotte de Witte")
    assert await repo.count() == 0

    removed_again = await repo.unlike("Charlotte de Witte")
    assert removed_again is False


async def test_list_all_and_get_liked_keys(repo: SQLiteLikedArtistRepository) -> None:
    await repo.like("Amelie Lens")
    await repo.like("Tale of Us")

    all_artists = await repo.list_all()
    assert len(all_artists) == 2
    names = {a.artist_name for a in all_artists}
    assert "Amelie Lens" in names
    assert "Tale of Us" in names

    keys = await repo.get_liked_keys()
    assert len(keys) == 2
    assert "amelie lens" in keys
    assert "tale of us" in keys
