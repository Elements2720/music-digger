"""Tests for the hybrid SQLite + LanceDB DJ set repository."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from data.datasources.local.lancedb_client import SET_VECTOR_SCHEMA, LanceDBClient
from data.datasources.local.sqlite_client import SQLiteClient
from data.repositories.set_repository import HybridSetRepository
from domain.entities.dj_set import DJSet, Passage, TrackMatch
from domain.entities.track import Track
from domain.value_objects.audio_features import (
    BPM,
    CamelotKey,
    EmbeddingVector,
    TimeRange,
)

_DIMENSION = 512


def _vector(seed: float) -> EmbeddingVector:
    # One-hot-ish directions so different seeds are NOT parallel (constant
    # vectors would share cosine 1.0). Values are float16-exact.
    peak = min(int(seed), _DIMENSION - 1)
    values = [0.1] * _DIMENSION
    values[peak] = 0.9
    return EmbeddingVector(values=values, dimension=_DIMENSION)


def _match(track_id: str) -> TrackMatch:
    return TrackMatch(
        track=Track(
            id=track_id,
            title=f"Song {track_id}",
            artist="Artist",
            bpm=BPM(128.0),
            key=CamelotKey("8A"),
            genre="Techno",
        ),
        similarity_score=0.9,
    )


def _set(
    set_id: str,
    *,
    passages: tuple[Passage, ...] = (),
    embedding: EmbeddingVector | None = None,
    **extra: object,
) -> DJSet:
    return DJSet(
        id=set_id,
        title=f"Set {set_id}",
        source_url=f"https://sound.test/{set_id}",
        duration_seconds=600.0,
        artist="Test DJ",
        thumbnail_url="https://img.test/x.jpg",
        bpm_min=BPM(126.0),
        bpm_max=BPM(132.0),
        embedding=embedding,
        passages=passages,
        **extra,  # type: ignore[arg-type]
    )


def _passage(
    start: float, *, embedding: EmbeddingVector | None = None, identified: bool = True
) -> Passage:
    return Passage(
        time_range=TimeRange(start, start + 120.0),
        bpm=BPM(128.5),
        key=CamelotKey("8A"),
        exact_id_match=identified,
        exact_id_title="ID Track" if identified else None,
        exact_id_artist="ID Artist" if identified else None,
        exact_id_source="shazam" if identified else None,
        embedding=embedding,
        closest_matches=(_match("itunes:1"),),
    )


@pytest.fixture
async def repository(
    tmp_path,
) -> AsyncIterator[tuple[HybridSetRepository, SQLiteClient]]:
    sqlite = SQLiteClient(tmp_path / "app.db")
    # The real set vector schema (512-dim float16) exercises the production path.
    vectors = LanceDBClient(
        tmp_path / "lancedb",
        table_name="set_vectors",
        schema=SET_VECTOR_SCHEMA,
        vector_dimension=_DIMENSION,
    )
    await sqlite.connect()
    await vectors.connect()
    yield HybridSetRepository(sqlite, vectors), sqlite
    await vectors.close()
    await sqlite.close()


async def test_save_and_get_round_trips_all_fields(
    repository: tuple[HybridSetRepository, SQLiteClient],
) -> None:
    hybrid, _ = repository
    dj_set = _set(
        "set-1",
        passages=(
            _passage(0.0, embedding=_vector(0.0)),
            _passage(120.0, identified=False),
        ),
        embedding=_vector(0.0),
    )

    await hybrid.save(dj_set)
    loaded = await hybrid.get_by_id("set-1")

    assert loaded is not None
    assert loaded.title == "Set set-1"
    assert loaded.artist == "Test DJ"
    assert loaded.thumbnail_url == "https://img.test/x.jpg"
    assert loaded.source_url == "https://sound.test/set-1"
    assert loaded.duration_seconds == pytest.approx(600.0)
    assert loaded.bpm_min == BPM(126.0)
    assert loaded.bpm_max == BPM(132.0)
    assert loaded.embedding is not None
    assert loaded.embedding.dimension == _DIMENSION
    assert loaded.embedding.values[0] == pytest.approx(0.9, abs=1e-3)
    assert len(loaded.passages) == 2

    first = loaded.passages[0]
    assert first.time_range == TimeRange(0.0, 120.0)
    assert first.bpm == BPM(128.5)
    assert first.key == CamelotKey("8A")
    assert first.exact_id_match is True
    assert first.exact_id_title == "ID Track"
    assert first.exact_id_artist == "ID Artist"
    assert first.exact_id_source == "shazam"
    assert first.embedding is not None
    assert first.embedding.values[0] == pytest.approx(0.9, abs=1e-3)
    assert first.closest_matches[0].track.id == "itunes:1"
    assert first.closest_matches[0].track.bpm == BPM(128.0)
    assert first.closest_matches[0].similarity_score == pytest.approx(0.9)

    # Unidentified passages stay unidentified after the round trip.
    assert loaded.passages[1].exact_id_match is False
    assert loaded.passages[1].exact_id_source is None


async def test_save_without_embedding_keeps_metadata_only(
    repository: tuple[HybridSetRepository, SQLiteClient],
) -> None:
    hybrid, _ = repository
    await hybrid.save(_set("set-1", passages=(_passage(0.0),)))

    loaded = await hybrid.get_by_id("set-1")
    assert loaded is not None
    assert loaded.embedding is None


async def test_get_by_id_returns_none_for_missing(
    repository: tuple[HybridSetRepository, SQLiteClient],
) -> None:
    hybrid, _ = repository
    assert await hybrid.get_by_id("missing") is None


async def test_resaving_replaces_passages_idempotently(
    repository: tuple[HybridSetRepository, SQLiteClient],
) -> None:
    hybrid, _ = repository
    await hybrid.save(_set("set-1", passages=(_passage(0.0), _passage(120.0))))
    # Re-analysis produces a different passage layout.
    await hybrid.save(_set("set-1", passages=(_passage(0.0), _passage(300.0))))

    loaded = await hybrid.get_by_id("set-1")
    assert loaded is not None
    assert [p.time_range.start_seconds for p in loaded.passages] == [0.0, 300.0]


async def test_find_similar_sets_orders_by_similarity(
    repository: tuple[HybridSetRepository, SQLiteClient],
) -> None:
    hybrid, _ = repository
    await hybrid.save(_set("set-a", passages=(), embedding=_vector(0.0)))
    await hybrid.save(_set("set-b", passages=(), embedding=_vector(1.0)))

    matches = await hybrid.find_similar_sets(_vector(0.0), limit=2)

    assert [match.dj_set.id for match in matches] == ["set-a", "set-b"]
    assert matches[0].similarity_score == pytest.approx(1.0, abs=1e-3)
    assert matches[0].similarity_percent == 100.0
    assert matches[1].similarity_percent < 100.0


async def test_delete_removes_sqlite_and_vector_rows(
    repository: tuple[HybridSetRepository, SQLiteClient],
) -> None:
    hybrid, sqlite = repository
    await hybrid.save(_set("set-1", passages=(_passage(0.0),), embedding=_vector(0.0)))

    assert await hybrid.delete("set-1") is True
    assert await hybrid.get_by_id("set-1") is None
    assert await hybrid.count() == 0
    leftover = await sqlite.fetchall(
        "SELECT * FROM set_passages WHERE set_id = 'set-1'"
    )
    assert leftover == []
    assert await hybrid.find_similar_sets(_vector(0.0), limit=5) == ()


async def test_delete_missing_set_returns_false(
    repository: tuple[HybridSetRepository, SQLiteClient],
) -> None:
    hybrid, _ = repository
    assert await hybrid.delete("missing") is False


async def test_list_all_returns_saved_sets(
    repository: tuple[HybridSetRepository, SQLiteClient],
) -> None:
    hybrid, _ = repository
    await hybrid.save(_set("set-1", passages=(_passage(0.0),), embedding=_vector(0.0)))
    await hybrid.save(_set("set-2", passages=(), embedding=_vector(1.0)))

    sets = await hybrid.list_all(limit=10)

    assert await hybrid.count() == 2
    assert {dj_set.id for dj_set in sets} == {"set-1", "set-2"}
    # list_all hydrates passages too (same path as get_by_id).
    first = next(dj_set for dj_set in sets if dj_set.id == "set-1")
    assert len(first.passages) == 1


async def test_list_all_respects_limit(
    repository: tuple[HybridSetRepository, SQLiteClient],
) -> None:
    hybrid, _ = repository
    await hybrid.save(_set("set-1", passages=()))
    await hybrid.save(_set("set-2", passages=()))

    assert len(await hybrid.list_all(limit=1)) == 1
    assert await hybrid.list_all(limit=0) == ()
