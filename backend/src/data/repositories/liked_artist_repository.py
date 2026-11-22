"""SQLite implementation of ``ILikedArtistRepository``."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from domain.entities.track import LikedArtist
from domain.interfaces.repositories import ILikedArtistRepository

from ..datasources.local.sqlite_client import SQLiteClient
from ..normalization import normalize_artist_key

_UPSERT_SQL = """
INSERT INTO liked_artists (artist_name, normalized_key)
VALUES (?, ?)
ON CONFLICT(normalized_key) DO UPDATE SET
    artist_name = excluded.artist_name
"""


class SQLiteLikedArtistRepository(ILikedArtistRepository):
    """Persist and query user-liked artists in SQLite with in-memory caching."""

    def __init__(self, sqlite: SQLiteClient) -> None:
        self._sqlite = sqlite
        self._lock = asyncio.Lock()
        self._liked_keys: frozenset[str] | None = None

    def _invalidate_cache(self) -> None:
        self._liked_keys = None

    async def like(self, artist_name: str) -> LikedArtist:
        """Like an artist idempotently and return the persisted LikedArtist."""
        clean_name = artist_name.strip()
        norm_key = normalize_artist_key(clean_name)
        await self._sqlite.execute(_UPSERT_SQL, (clean_name, norm_key))
        self._invalidate_cache()
        row = await self._sqlite.fetchone(
            "SELECT artist_name, normalized_key, created_at FROM liked_artists WHERE normalized_key = ?",
            (norm_key,),
        )
        if row is None:
            return LikedArtist(artist_name=clean_name, normalized_key=norm_key)
        return LikedArtist(
            artist_name=str(row["artist_name"]),
            normalized_key=str(row["normalized_key"]),
            created_at=str(row["created_at"]) if row["created_at"] else None,
        )

    async def unlike(self, artist_name: str) -> bool:
        """Unlike an artist by name, returning True if removed."""
        clean_name = artist_name.strip()
        norm_key = normalize_artist_key(clean_name)
        cursor = await self._sqlite.execute(
            "DELETE FROM liked_artists WHERE normalized_key = ?",
            (norm_key,),
        )
        self._invalidate_cache()
        return bool(cursor.rowcount and cursor.rowcount > 0)

    async def is_liked(self, artist_name: str) -> bool:
        """Return True if the artist is liked."""
        keys = await self.get_liked_keys()
        return normalize_artist_key(artist_name.strip()) in keys

    async def list_all(self) -> Sequence[LikedArtist]:
        """Return all liked artists ordered by creation date descending."""
        rows = await self._sqlite.fetchall(
            "SELECT artist_name, normalized_key, created_at FROM liked_artists "
            "ORDER BY created_at DESC, artist_name COLLATE NOCASE ASC"
        )
        return tuple(
            LikedArtist(
                artist_name=str(r["artist_name"]),
                normalized_key=str(r["normalized_key"]),
                created_at=str(r["created_at"]) if r["created_at"] else None,
            )
            for r in rows
        )

    async def get_liked_keys(self) -> frozenset[str]:
        """Return frozenset of normalized keys of all liked artists."""
        if self._liked_keys is not None:
            return self._liked_keys
        async with self._lock:
            if self._liked_keys is not None:
                return self._liked_keys
            rows = await self._sqlite.fetchall(
                "SELECT normalized_key FROM liked_artists"
            )
            keys = frozenset(str(r["normalized_key"]) for r in rows)
            self._liked_keys = keys
            return keys

    async def count(self) -> int:
        """Return count of liked artists."""
        row = await self._sqlite.fetchone("SELECT COUNT(*) AS total FROM liked_artists")
        return int(row["total"] or 0) if row else 0
