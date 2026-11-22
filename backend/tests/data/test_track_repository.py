"""Tests for the hybrid SQLite + LanceDB track repository."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from data.datasources.local.lancedb_client import LanceDBClient
from data.datasources.local.sqlite_client import SQLiteClient
from data.repositories.track_repository import HybridTrackRepository
from domain.entities.search import SearchFilter
from domain.entities.track import Track
from domain.value_objects.audio_features import BPM, CamelotKey, EmbeddingVector


@pytest.fixture
async def repository(tmp_path) -> AsyncIterator[HybridTrackRepository]:
    sqlite = SQLiteClient(tmp_path / "app.db")
    vectors = LanceDBClient(tmp_path / "lancedb", vector_dimension=8)
    await sqlite.connect()
    await vectors.connect()
    yield HybridTrackRepository(sqlite, vectors)
    await vectors.close()
    await sqlite.close()


def _embedding(base: float = 0.1) -> EmbeddingVector:
    # A gentle ramp gives every vector a distinct direction while staying unit-ish.
    return EmbeddingVector(values=tuple(base + 0.01 * index for index in range(8)))


def _track(
    track_id: str,
    *,
    title: str = "Song",
    artist: str = "Artist",
    embedding: EmbeddingVector | None = None,
    preview_url: str | None = "https://example.test/preview.m4a",
    **extra: object,
) -> Track:
    return Track(
        id=track_id,
        title=title,
        artist=artist,
        embedding=embedding,
        source="itunes",
        external_id=track_id.replace("itunes:", ""),
        preview_url=preview_url,
        duration_seconds=300.0,
        **extra,  # type: ignore[arg-type]
    )


async def test_upsert_persists_metadata_and_vectors(
    repository: HybridTrackRepository,
) -> None:
    track = _track("itunes:1", embedding=_embedding())
    assert await repository.upsert_many([track]) == 1
    assert await repository.count() == 1
    assert await repository.count_embedded() == 1

    loaded = await repository.get_by_id("itunes:1")
    assert loaded is not None
    assert loaded.title == "Song"
    assert loaded.embedding is not None
    assert loaded.embedding.dimension == 8


async def test_upsert_dedups_by_normalized_artist_title(
    repository: HybridTrackRepository,
) -> None:
    await repository.upsert_many(
        [_track("itunes:1", title="Song", artist="Artist", embedding=_embedding())]
    )
    await repository.upsert_many(
        [_track("itunes:2", title="SONG", artist="artist", embedding=_embedding())]
    )
    assert await repository.count() == 1

    second = await repository.get_by_external_id("itunes", "2")
    assert second is not None
    assert second.id == "itunes:1", "the duplicate must reuse the existing row id"


async def test_upsert_preserves_heard_flag(repository: HybridTrackRepository) -> None:
    await repository.upsert_many([_track("itunes:1", embedding=_embedding())])
    await repository.mark_heard("itunes:1")
    await repository.upsert_many([_track("itunes:1", embedding=_embedding())])
    assert await repository.get_heard_ids() == frozenset({"itunes:1"})


async def test_find_similar_orders_by_similarity(
    repository: HybridTrackRepository,
) -> None:
    near = _track("itunes:1", embedding=_embedding(0.1))
    far = _track("itunes:2", title="Far", artist="Other", embedding=_embedding(0.9))
    await repository.upsert_many([near, far])

    matches = await repository.find_similar(
        _embedding(0.1),
        SearchFilter(limit=2),
    )
    assert [match.track.id for match in matches] == ["itunes:1", "itunes:2"]
    assert matches[0].similarity_score > matches[1].similarity_score
    assert matches[0].is_exact_id is False


async def test_find_similar_applies_vector_filters(
    repository: HybridTrackRepository,
) -> None:
    techno = _track(
        "itunes:1",
        embedding=_embedding(0.1),
        genre="Techno",
        bpm=BPM(128),
        key=CamelotKey("8A"),
    )
    house = _track(
        "itunes:2",
        title="House Song",
        artist="Other",
        embedding=_embedding(0.1),
        genre="House",
        bpm=BPM(124),
        key=CamelotKey("9A"),
    )
    await repository.upsert_many([techno, house])

    genre_matches = await repository.find_similar(
        _embedding(0.1),
        SearchFilter(limit=5, genre_filter="techno"),
    )
    assert [match.track.id for match in genre_matches] == ["itunes:1"]

    bpm_matches = await repository.find_similar(
        _embedding(0.1),
        SearchFilter(limit=5, bpm_min=125),
    )
    assert [match.track.id for match in bpm_matches] == ["itunes:1"]

    key_matches = await repository.find_similar(
        _embedding(0.1),
        SearchFilter(limit=5, camelot_keys=(CamelotKey("8A"),)),
    )
    assert [match.track.id for match in key_matches] == ["itunes:1"]


async def test_find_similar_excludes_heard(
    repository: HybridTrackRepository,
) -> None:
    await repository.upsert_many([_track("itunes:1", embedding=_embedding())])
    await repository.mark_heard("itunes:1")
    matches = await repository.find_similar(
        _embedding(),
        SearchFilter(limit=5, exclude_heard=True),
    )
    assert matches == ()


async def test_find_by_filter_is_metadata_only(
    repository: HybridTrackRepository,
) -> None:
    await repository.upsert_many(
        [
            _track(
                "itunes:1",
                genre="Techno",
                bpm=BPM(128),
                key=CamelotKey("8A"),
            ),
            _track(
                "itunes:2",
                title="Other",
                artist="B",
                genre="House",
                bpm=BPM(124),
                key=CamelotKey("9A"),
            ),
        ]
    )
    techno = await repository.find_by_filter(
        SearchFilter(limit=5, genre_filter="TECHNO")
    )
    assert [track.id for track in techno] == ["itunes:1"]
    fast = await repository.find_by_filter(SearchFilter(limit=5, bpm_min=126))
    assert [track.id for track in fast] == ["itunes:1"]
    keys = await repository.find_by_filter(
        SearchFilter(limit=5, camelot_keys=(CamelotKey("9A"),))
    )
    assert [track.id for track in keys] == ["itunes:2"]


async def test_get_many_preserves_request_order(
    repository: HybridTrackRepository,
) -> None:
    await repository.upsert_many(
        [_track("itunes:1"), _track("itunes:2", title="Second", artist="B")]
    )
    tracks = await repository.get_many(["itunes:2", "missing", "itunes:1"])
    assert [track.id for track in tracks] == ["itunes:2", "itunes:1"]


async def test_get_by_id_returns_none_for_missing(
    repository: HybridTrackRepository,
) -> None:
    assert await repository.get_by_id("missing") is None


async def test_upsert_empty_batch_is_a_noop(
    repository: HybridTrackRepository,
) -> None:
    assert await repository.upsert_many([]) == 0
    assert await repository.count() == 0
    assert await repository.count_embedded() == 0


async def test_lancedb_rejects_wrong_vector_dimension(tmp_path) -> None:
    vectors = LanceDBClient(tmp_path / "lancedb", vector_dimension=4)
    await vectors.connect()
    try:
        with pytest.raises(ValueError, match="dimension"):
            await vectors.upsert_many(
                [{"id": "a", "vector": [0.1, 0.2, 0.3, 0.4, 0.5]}]
            )
    finally:
        await vectors.close()


async def test_list_unembedded_returns_only_indexable_tracks(
    repository: HybridTrackRepository,
) -> None:
    good = _track("itunes:1", title="Alpha")
    no_preview = _track("itunes:2", title="Beta", preview_url=None)
    await repository.upsert_many([good, no_preview])

    pending = await repository.list_unembedded(limit=10)

    assert [track.id for track in pending] == ["itunes:1"]


async def test_list_unembedded_skips_tracks_with_too_many_failures(
    repository: HybridTrackRepository,
) -> None:
    await repository.upsert_many([_track("itunes:1")])

    await repository.mark_index_failed("itunes:1")
    await repository.mark_index_failed("itunes:1")

    assert len(await repository.list_unembedded(limit=10, max_failures=3)) == 1
    assert await repository.list_unembedded(limit=10, max_failures=2) == ()


async def test_list_reindexable_includes_embedded_tracks(
    repository: HybridTrackRepository,
) -> None:
    embedded = _track("itunes:1", title="Alpha", embedding=_embedding())
    pending = _track("itunes:2", title="Beta")
    no_preview = _track("itunes:3", title="Gamma", preview_url=None)
    await repository.upsert_many([embedded, pending, no_preview])

    reindexable = await repository.list_reindexable(limit=10)

    assert [track.id for track in reindexable] == ["itunes:1", "itunes:2"]


async def test_reset_embeddings_clears_vectors_but_keeps_metadata(
    repository: HybridTrackRepository,
) -> None:
    first = _track(
        "itunes:1",
        title="Alpha",
        embedding=_embedding(),
        bpm=BPM(125.0),
        key=CamelotKey("8A"),
    )
    second = _track("itunes:2", title="Beta")
    await repository.upsert_many([first, second])

    cleared = await repository.reset_embeddings()

    assert cleared == 1
    assert await repository.count_embedded() == 0
    survivor = await repository.get_by_id("itunes:1")
    assert survivor is not None
    assert survivor.title == "Alpha"
    assert survivor.embedding is None
    assert survivor.bpm is None
    assert survivor.key is None
    # Failure counters are wiped too so a fresh run starts clean.
    await repository.mark_index_failed("itunes:1")
    assert len(await repository.list_reindexable(limit=10, max_failures=3)) == 2


async def test_reset_embeddings_on_empty_catalog_is_a_noop(
    repository: HybridTrackRepository,
) -> None:
    assert await repository.reset_embeddings() == 0
    assert await repository.count_embedded() == 0


async def test_list_embedded_returns_recently_indexed_first(
    repository: HybridTrackRepository,
) -> None:
    await repository.upsert_many(
        [_track("itunes:1", title="Alpha", embedding=_embedding())]
    )
    await repository.upsert_many(
        [_track("itunes:2", title="Beta", embedding=_embedding())]
    )
    # No embedding: is_embedded stays 0, so this row is never listed.
    await repository.upsert_many([_track("itunes:3", title="Gamma")])

    embedded = await repository.list_embedded(limit=10)

    assert [track.id for track in embedded] == ["itunes:2", "itunes:1"]
    # Listing views are lightweight: rows come back as a tuple and vectors
    # are not hydrated from LanceDB (only get_by_id loads embeddings).
    assert await repository.list_embedded(limit=1) == (embedded[0],)
    assert await repository.list_embedded(limit=10, offset=2) == ()


async def test_updating_features_keeps_embedding_flag(
    repository: HybridTrackRepository,
) -> None:
    """The indexer re-upserts a track with bpm/key/embedding after analysis."""
    await repository.upsert_many([_track("itunes:1")])
    analyzed = _track(
        "itunes:1",
        embedding=_embedding(0.5),
        bpm=BPM(126.0),
        key=CamelotKey("8A"),
    )

    await repository.upsert_many([analyzed])

    loaded = await repository.get_by_id("itunes:1")
    assert loaded is not None
    assert loaded.bpm == BPM(126.0)
    assert loaded.key == CamelotKey("8A")
    assert loaded.embedding is not None
    assert await repository.count_embedded() == 1
    similar = await repository.find_similar(_embedding(0.5), SearchFilter(limit=5))
    assert [match.track.id for match in similar] == ["itunes:1"]


async def test_legacy_databases_gain_the_index_failures_column(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    """A Phase 2 database (schema without index_failures) migrates on connect."""
    import aiosqlite

    from data.datasources.local.sqlite_client import SCHEMA

    legacy_path = tmp_path / "legacy.db"
    legacy_schema = "\n".join(
        line for line in SCHEMA.splitlines() if "index_failures" not in line
    )
    async with aiosqlite.connect(legacy_path) as connection:
        await connection.executescript(legacy_schema)
        await connection.execute(
            "INSERT INTO tracks (id, title, artist, normalized_key) "
            "VALUES ('itunes:1', 'Song', 'Artist', 'artist song')"
        )
        await connection.commit()

    sqlite = SQLiteClient(legacy_path)
    await sqlite.connect()
    try:
        row = await sqlite.fetchone(
            "SELECT index_failures FROM tracks WHERE id = 'itunes:1'"
        )
        assert row is not None
        assert row["index_failures"] == 0
    finally:
        await sqlite.close()


async def test_search_tracks_matches_title_or_artist_case_insensitively(
    repository: HybridTrackRepository,
) -> None:
    await repository.upsert_many(
        [
            _track("itunes:1", title="Night Drive", artist="Solomun"),
            _track("itunes:2", title="Sunrise", artist="Tale Of Us"),
            _track("itunes:3", title="Horizon", artist="ARTBAT"),
        ]
    )

    by_title = await repository.search_tracks("night")
    assert [track.id for track in by_title] == ["itunes:1"]

    by_artist = await repository.search_tracks("tale of")
    assert [track.id for track in by_artist] == ["itunes:2"]

    assert await repository.search_tracks("") == ()
    assert await repository.search_tracks("   ") == ()


async def test_search_tracks_respects_the_limit_and_orders_embedded_first(
    repository: HybridTrackRepository,
) -> None:
    await repository.upsert_many(
        [
            _track("itunes:1", title="Alpha", artist="A", embedding=None),
            _track("itunes:2", title="Alpha Two", artist="B", embedding=_embedding()),
            _track("itunes:3", title="Alpha Three", artist="C", embedding=None),
        ]
    )

    hits = await repository.search_tracks("alpha", limit=2)
    assert len(hits) == 2
    assert hits[0].id == "itunes:2", "embedded tracks surface first for digging"
    assert await repository.search_tracks("alpha", limit=0) == ()


async def test_set_heard_toggles_both_ways(repository: HybridTrackRepository) -> None:
    await repository.upsert_many([_track("itunes:1", embedding=_embedding())])

    await repository.set_heard("itunes:1", True)
    assert await repository.get_heard_ids() == frozenset({"itunes:1"})

    await repository.set_heard("itunes:1", False)
    assert await repository.get_heard_ids() == frozenset()


async def test_upsert_and_get_local_track(repository: HybridTrackRepository) -> None:
    local_track = Track(
        id="local:abc123456789",
        title="Moon Rocks",
        artist="Enrico Sangiuliano",
        source="local",
        local_path="/music/moon_rocks.mp3",
        duration_seconds=360.0,
        embedding=_embedding(),
    )
    await repository.upsert_many([local_track])
    loaded = await repository.get_by_id("local:abc123456789")
    assert loaded is not None
    assert loaded.id == "local:abc123456789"
    assert loaded.source == "local"
    assert loaded.local_path == "/music/moon_rocks.mp3"
    assert loaded.embedding is not None

    # Test get_embedded_ids
    embedded_ids = await repository.get_embedded_ids(
        ["local:abc123456789", "nonexistent"]
    )
    assert embedded_ids == frozenset({"local:abc123456789"})

