"""Hybrid track repository: SQLite metadata plus LanceDB vectors."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from domain.entities.dj_set import TrackMatch
from domain.entities.search import SearchFilter
from domain.entities.track import Track
from domain.interfaces.repositories import ITrackRepository
from domain.value_objects.audio_features import EmbeddingVector

from ..datasources.local.lancedb_client import LanceDBClient
from ..datasources.local.sqlite_client import SQLiteClient
from ..mappers.track_mapper import row_to_track, track_to_row, track_to_vector_row

_UPSERT_SQL = """
INSERT INTO tracks (
    id, itunes_track_id, title, artist, normalized_key, album, genre,
    duration_sec, release_year, preview_url, artwork_url, store_url, bpm,
    camelot_key, is_embedded, is_heard, source, external_id, isrc
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    itunes_track_id = excluded.itunes_track_id,
    title = excluded.title,
    artist = excluded.artist,
    normalized_key = excluded.normalized_key,
    album = excluded.album,
    genre = excluded.genre,
    duration_sec = excluded.duration_sec,
    release_year = excluded.release_year,
    preview_url = excluded.preview_url,
    artwork_url = excluded.artwork_url,
    store_url = excluded.store_url,
    bpm = excluded.bpm,
    camelot_key = excluded.camelot_key,
    is_embedded = MAX(tracks.is_embedded, excluded.is_embedded),
    is_heard = MAX(tracks.is_heard, excluded.is_heard),
    source = excluded.source,
    external_id = excluded.external_id,
    isrc = excluded.isrc,
    updated_at = CURRENT_TIMESTAMP
"""


class HybridTrackRepository(ITrackRepository):
    """Coordinate relational metadata with the disk-backed vector index."""

    def __init__(self, sqlite: SQLiteClient, vectors: LanceDBClient) -> None:
        self._sqlite = sqlite
        self._vectors = vectors

    async def upsert_many(self, tracks: Sequence[Track]) -> int:
        if not tracks:
            return 0

        vector_tracks: list[Track] = []
        async with self._sqlite.transaction() as connection:
            for track in tracks:
                row = track_to_row(track)
                existing_id = await self._find_existing_id(connection, row)
                if existing_id is not None and existing_id != row["id"]:
                    row["id"] = existing_id
                    if track.embedding is not None:
                        vector_tracks.append(replace(track, id=existing_id))
                elif track.embedding is not None:
                    vector_tracks.append(track)
                await connection.execute(_UPSERT_SQL, self._upsert_parameters(row))

        if vector_tracks:
            await self._vectors.upsert_many(
                [track_to_vector_row(track) for track in vector_tracks]
            )
        return len(tracks)

    async def get_by_id(self, track_id: str) -> Track | None:
        row = await self._sqlite.fetchone(
            "SELECT * FROM tracks WHERE id = ?",
            (track_id,),
        )
        if row is None:
            return None
        track = row_to_track(row)
        if row["is_embedded"]:
            vector = await self._vectors.get_vector(track_id)
            if vector is not None:
                track = track.with_embedding(EmbeddingVector(values=vector))
        return track

    async def get_by_external_id(self, source: str, external_id: str) -> Track | None:
        row = await self._sqlite.fetchone(
            """
            SELECT * FROM tracks
            WHERE (source = ? AND external_id = ?)
               OR (source = 'itunes' AND itunes_track_id = ?)
            LIMIT 1
            """,
            (source, external_id, external_id),
        )
        return row_to_track(row) if row is not None else None

    async def get_many(self, track_ids: Sequence[str]) -> Sequence[Track]:
        if not track_ids:
            return ()
        placeholders = ", ".join("?" for _ in track_ids)
        rows = await self._sqlite.fetchall(
            f"SELECT * FROM tracks WHERE id IN ({placeholders})",
            tuple(track_ids),
        )
        by_id = {row["id"]: row_to_track(row) for row in rows}
        return tuple(by_id[track_id] for track_id in track_ids if track_id in by_id)

    async def find_similar(
        self,
        embedding: EmbeddingVector,
        search_filter: SearchFilter,
    ) -> Sequence[TrackMatch]:
        heard_ids = (
            await self.get_heard_ids() if search_filter.exclude_heard else frozenset()
        )
        where = self._vector_where(search_filter, heard_ids)
        vector_matches = await self._vectors.search(
            embedding.values,
            limit=search_filter.limit,
            where=where,
        )
        tracks = await self.get_many([match.track_id for match in vector_matches])
        by_id = {track.id: track for track in tracks}
        matches: list[TrackMatch] = []
        for vector_match in vector_matches:
            track = by_id.get(vector_match.track_id)
            if track is None:
                continue
            if search_filter.exclude_heard and track.id in heard_ids:
                continue
            matches.append(
                TrackMatch(
                    track=track,
                    similarity_score=vector_match.similarity,
                )
            )
        return tuple(matches)

    async def find_by_filter(self, search_filter: SearchFilter) -> Sequence[Track]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if search_filter.bpm_min is not None:
            clauses.append("bpm >= ?")
            parameters.append(search_filter.bpm_min)
        if search_filter.bpm_max is not None:
            clauses.append("bpm <= ?")
            parameters.append(search_filter.bpm_max)
        if search_filter.camelot_keys:
            placeholders = ", ".join("?" for _ in search_filter.camelot_keys)
            clauses.append(f"camelot_key IN ({placeholders})")
            parameters.extend(key.notation for key in search_filter.camelot_keys)
        if search_filter.exclude_heard:
            clauses.append("is_heard = 0")
        if search_filter.genre_filter is not None:
            clauses.append("LOWER(genre) = LOWER(?)")
            parameters.append(search_filter.genre_filter)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(search_filter.limit)
        rows = await self._sqlite.fetchall(
            f"""
            SELECT * FROM tracks
            {where}
            ORDER BY artist COLLATE NOCASE, title COLLATE NOCASE
            LIMIT ?
            """,
            tuple(parameters),
        )
        return tuple(row_to_track(row) for row in rows)

    async def search_tracks(
        self, query: str, limit: int = 30
    ) -> Sequence[Track]:
        if limit <= 0:
            return ()
        needle = query.strip()
        if not needle:
            return ()
        pattern = f"%{needle}%"
        rows = await self._sqlite.fetchall(
            """
            SELECT * FROM tracks
            WHERE title LIKE ? OR artist LIKE ?
            ORDER BY is_embedded DESC, artist COLLATE NOCASE, title COLLATE NOCASE
            LIMIT ?
            """,
            (pattern, pattern, limit),
        )
        return tuple(row_to_track(row) for row in rows)

    async def mark_heard(self, track_id: str) -> None:
        await self._sqlite.execute(
            """
            UPDATE tracks
            SET is_heard = 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (track_id,),
        )

    async def set_heard(self, track_id: str, heard: bool) -> None:
        await self._sqlite.execute(
            """
            UPDATE tracks
            SET is_heard = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (1 if heard else 0, track_id),
        )

    async def get_heard_ids(self) -> frozenset[str]:
        rows = await self._sqlite.fetchall("SELECT id FROM tracks WHERE is_heard = 1")
        return frozenset(str(row["id"]) for row in rows)

    async def count(self) -> int:
        row = await self._sqlite.fetchone("SELECT COUNT(*) AS total FROM tracks")
        return int(row["total"]) if row is not None else 0

    async def count_embedded(self) -> int:
        row = await self._sqlite.fetchone(
            "SELECT COUNT(*) AS total FROM tracks WHERE is_embedded = 1"
        )
        return int(row["total"]) if row is not None else 0

    async def list_unembedded(
        self,
        limit: int = 100,
        *,
        max_failures: int = 3,
    ) -> Sequence[Track]:
        if limit <= 0:
            return ()
        rows = await self._sqlite.fetchall(
            """
            SELECT * FROM tracks
            WHERE is_embedded = 0
              AND preview_url IS NOT NULL
              AND index_failures < ?
            ORDER BY created_at, id
            LIMIT ?
            """,
            (max_failures, limit),
        )
        return tuple(row_to_track(row) for row in rows)

    async def list_embedded(
        self, limit: int = 20, *, offset: int = 0
    ) -> Sequence[Track]:
        if limit <= 0:
            return ()
        rows = await self._sqlite.fetchall(
            """
            SELECT * FROM tracks
            WHERE is_embedded = 1
            ORDER BY updated_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return tuple(row_to_track(row) for row in rows)

    async def mark_index_failed(self, track_id: str) -> None:
        await self._sqlite.execute(
            """
            UPDATE tracks
            SET index_failures = index_failures + 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (track_id,),
        )

    async def list_reindexable(
        self,
        limit: int = 100,
        *,
        max_failures: int = 3,
    ) -> Sequence[Track]:
        if limit <= 0:
            return ()
        rows = await self._sqlite.fetchall(
            """
            SELECT * FROM tracks
            WHERE preview_url IS NOT NULL
              AND index_failures < ?
            ORDER BY created_at, id
            LIMIT ?
            """,
            (max_failures, limit),
        )
        return tuple(row_to_track(row) for row in rows)

    async def reset_embeddings(self) -> int:
        cleared = await self.count_embedded()
        await self._vectors.clear_all()
        await self._sqlite.execute(
            """
            UPDATE tracks
            SET is_embedded = 0, bpm = NULL, camelot_key = NULL,
                index_failures = 0, updated_at = CURRENT_TIMESTAMP
            WHERE is_embedded = 1
            """
        )
        return cleared

    @staticmethod
    async def _find_existing_id(connection: Any, row: dict[str, Any]) -> str | None:
        itunes_id = row["itunes_track_id"]
        if itunes_id is not None:
            query = (
                "SELECT id FROM tracks "
                "WHERE normalized_key = ? OR itunes_track_id = ? LIMIT 1"
            )
            parameters = (row["normalized_key"], itunes_id)
        else:
            query = "SELECT id FROM tracks WHERE normalized_key = ? LIMIT 1"
            parameters = (row["normalized_key"],)
        async with connection.execute(query, parameters) as cursor:
            existing = await cursor.fetchone()
        return str(existing["id"]) if existing is not None else None

    @staticmethod
    def _upsert_parameters(row: dict[str, Any]) -> tuple[Any, ...]:
        return (
            row["id"],
            row["itunes_track_id"],
            row["title"],
            row["artist"],
            row["normalized_key"],
            row["album"],
            row["genre"],
            row["duration_sec"],
            row["release_year"],
            row["preview_url"],
            row["artwork_url"],
            row["store_url"],
            row["bpm"],
            row["camelot_key"],
            row["is_embedded"],
            row["source"],
            row["external_id"],
            row["isrc"],
        )

    @staticmethod
    def _vector_where(
        search_filter: SearchFilter,
        heard_ids: frozenset[str],
    ) -> str | None:
        clauses: list[str] = []
        if search_filter.bpm_min is not None:
            clauses.append(f"bpm >= {search_filter.bpm_min}")
        if search_filter.bpm_max is not None:
            clauses.append(f"bpm <= {search_filter.bpm_max}")
        if search_filter.camelot_keys:
            keys = ", ".join(
                "'" + key.notation.replace("'", "''") + "'"
                for key in search_filter.camelot_keys
            )
            clauses.append(f"camelot_key IN ({keys})")
        if search_filter.genre_filter is not None:
            genre = search_filter.genre_filter.replace("'", "''")
            clauses.append(f"lower(genre) = lower('{genre}')")
        if search_filter.exclude_heard and heard_ids:
            ids = ", ".join(
                "'" + track_id.replace("'", "''") + "'" for track_id in heard_ids
            )
            clauses.append(f"id NOT IN ({ids})")
        return " AND ".join(clauses) if clauses else None


__all__ = ["HybridTrackRepository"]
