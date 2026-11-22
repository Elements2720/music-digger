"""Hybrid DJ set repository: SQLite metadata plus LanceDB whole-set vectors."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from domain.entities.dj_set import DJSet, SetMatch
from domain.interfaces.repositories import ISetRepository
from domain.value_objects.audio_features import EmbeddingVector

from ..datasources.local.lancedb_client import LanceDBClient
from ..datasources.local.sqlite_client import SQLiteClient
from ..mappers.set_mapper import (
    passage_to_row,
    row_to_passage,
    row_to_set,
    set_to_row,
    set_to_vector_row,
)

LOGGER = logging.getLogger(__name__)

_SET_UPSERT_SQL = """
INSERT INTO dj_sets (
    id, title, source_url, duration_sec, artist, thumbnail_url, bpm_min, bpm_max
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    title = excluded.title,
    source_url = excluded.source_url,
    duration_sec = excluded.duration_sec,
    artist = excluded.artist,
    thumbnail_url = excluded.thumbnail_url,
    bpm_min = excluded.bpm_min,
    bpm_max = excluded.bpm_max,
    updated_at = CURRENT_TIMESTAMP
"""

_PASSAGE_INSERT_SQL = """
INSERT INTO set_passages (
    set_id, start_sec, end_sec, bpm, camelot_key, exact_id_match,
    exact_id_title, exact_id_artist, exact_id_source, embedding,
    closest_matches_json
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class HybridSetRepository(ISetRepository):
    """Coordinate relational set storage with the disk-backed vector index."""

    def __init__(self, sqlite: SQLiteClient, vectors: LanceDBClient) -> None:
        self._sqlite = sqlite
        self._vectors = vectors

    async def save(self, dj_set: DJSet) -> None:
        """Insert or replace a DJ set, its passages, and its set vector."""
        async with self._sqlite.transaction() as connection:
            row = set_to_row(dj_set)
            await connection.execute(
                _SET_UPSERT_SQL,
                (
                    row["id"],
                    row["title"],
                    row["source_url"],
                    row["duration_sec"],
                    row["artist"],
                    row["thumbnail_url"],
                    row["bpm_min"],
                    row["bpm_max"],
                ),
            )
            # Replace the passage block wholesale so re-analysis is idempotent.
            await connection.execute(
                "DELETE FROM set_passages WHERE set_id = ?", (dj_set.id,)
            )
            for passage in dj_set.passages:
                passage_row = passage_to_row(dj_set.id, passage)
                await connection.execute(
                    _PASSAGE_INSERT_SQL,
                    (
                        passage_row["set_id"],
                        passage_row["start_sec"],
                        passage_row["end_sec"],
                        passage_row["bpm"],
                        passage_row["camelot_key"],
                        passage_row["exact_id_match"],
                        passage_row["exact_id_title"],
                        passage_row["exact_id_artist"],
                        passage_row["exact_id_source"],
                        passage_row["embedding"],
                        passage_row["closest_matches_json"],
                    ),
                )

        if dj_set.embedding is not None:
            await self._vectors.upsert_many([set_to_vector_row(dj_set)])

    async def get_by_id(self, set_id: str) -> DJSet | None:
        row = await self._sqlite.fetchone(
            "SELECT * FROM dj_sets WHERE id = ?", (set_id,)
        )
        if row is None:
            return None
        dj_set = row_to_set(row)
        passage_rows = await self._sqlite.fetchall(
            """
            SELECT * FROM set_passages
            WHERE set_id = ?
            ORDER BY start_sec, end_sec
            """,
            (set_id,),
        )
        passages = tuple(row_to_passage(passage_row) for passage_row in passage_rows)
        if dj_set.embedding is None:
            vector = await self._vectors.get_vector(set_id)
            if vector is not None:
                dj_set = dj_set.with_embedding(EmbeddingVector(values=vector))
        # Rebuild with passages validated against the (possibly hydrated) set.
        return DJSet(
            id=dj_set.id,
            title=dj_set.title,
            source_url=dj_set.source_url,
            duration_seconds=dj_set.duration_seconds,
            artist=dj_set.artist,
            thumbnail_url=dj_set.thumbnail_url,
            bpm_min=dj_set.bpm_min,
            bpm_max=dj_set.bpm_max,
            embedding=dj_set.embedding,
            passages=passages,
        )

    async def list_all(self, limit: int = 20) -> Sequence[DJSet]:
        if limit <= 0:
            return ()
        rows = await self._sqlite.fetchall(
            "SELECT * FROM dj_sets ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        )
        sets: list[DJSet] = []
        for row in rows:
            found = await self.get_by_id(row["id"])
            if found is not None:
                sets.append(found)
        return tuple(sets)

    async def delete(self, set_id: str) -> bool:
        found = await self.get_by_id(set_id)
        if found is None:
            return False
        async with self._sqlite.transaction() as connection:
            await connection.execute(
                "DELETE FROM set_passages WHERE set_id = ?", (set_id,)
            )
            await connection.execute("DELETE FROM dj_sets WHERE id = ?", (set_id,))
        await self._vectors.delete_ids([set_id])
        return True

    async def count(self) -> int:
        row = await self._sqlite.fetchone("SELECT COUNT(*) AS total FROM dj_sets")
        return int(row["total"]) if row is not None else 0

    async def find_similar_sets(
        self,
        embedding: EmbeddingVector,
        *,
        limit: int = 12,
    ) -> Sequence[SetMatch]:
        if limit <= 0:
            return ()
        vector_matches = await self._vectors.search(embedding.values, limit=limit)
        matches: list[SetMatch] = []
        for vector_match in vector_matches:
            found = await self.get_by_id(vector_match.track_id)
            if found is None:
                continue
            matches.append(
                SetMatch(dj_set=found, similarity_score=vector_match.similarity)
            )
        return tuple(matches)


__all__ = ["HybridSetRepository"]
