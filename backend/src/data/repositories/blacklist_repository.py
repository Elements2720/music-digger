"""SQLite implementation of ``IBlacklistRepository``."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from domain.entities.track import BlacklistEntry
from domain.interfaces.repositories import IBlacklistRepository

from ..datasources.local.sqlite_client import SQLiteClient
from ..mappers.blacklist_mapper import row_to_blacklist

_UPSERT_SQL = """
INSERT INTO blacklist (
    kind, normalized_key, display_name, artist_name, track_title, reason
)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(kind, normalized_key) DO UPDATE SET
    display_name = excluded.display_name,
    artist_name = excluded.artist_name,
    track_title = excluded.track_title,
    reason = excluded.reason
"""

_SELECT_BY_KEY_SQL = """
SELECT id, kind, normalized_key, display_name, artist_name, track_title, reason, created_at
FROM blacklist
WHERE kind = ? AND normalized_key = ?
"""


class SQLiteBlacklistRepository(IBlacklistRepository):
    """Persist and query blacklisted artists and tracks in SQLite."""

    def __init__(self, sqlite: SQLiteClient) -> None:
        self._sqlite = sqlite
        self._lock = asyncio.Lock()
        self._blocked_artists: set[str] | None = None
        self._blocked_tracks: set[str] | None = None

    def _invalidate_cache(self) -> None:
        self._blocked_artists = None
        self._blocked_tracks = None

    async def _load_cache_if_needed(self) -> None:
        if self._blocked_artists is not None and self._blocked_tracks is not None:
            return
        async with self._lock:
            if self._blocked_artists is not None and self._blocked_tracks is not None:
                return
            rows = await self._sqlite.fetchall(
                "SELECT kind, normalized_key FROM blacklist"
            )
            artists: set[str] = set()
            tracks: set[str] = set()
            for r in rows:
                if r["kind"] == "artist":
                    artists.add(r["normalized_key"])
                elif r["kind"] == "track":
                    tracks.add(r["normalized_key"])
            self._blocked_artists = artists
            self._blocked_tracks = tracks

    async def add(self, entry: BlacklistEntry) -> BlacklistEntry:
        """Insert or update a blacklist entry and return the persisted entry."""
        parameters = (
            entry.kind,
            entry.normalized_key,
            entry.display_name,
            entry.artist_name,
            entry.track_title,
            entry.reason,
        )
        await self._sqlite.execute(_UPSERT_SQL, parameters)
        self._invalidate_cache()
        row = await self._sqlite.fetchone(
            _SELECT_BY_KEY_SQL, (entry.kind, entry.normalized_key)
        )
        if row is None:
            raise RuntimeError(
                f"Failed to fetch blacklisted entry {entry.normalized_key!r}"
            )
        return row_to_blacklist(row)

    async def remove(self, entry_id: int) -> bool:
        """Remove a blacklist entry by ID, returning True if a row was deleted."""
        cursor = await self._sqlite.execute(
            "DELETE FROM blacklist WHERE id = ?", (entry_id,)
        )
        deleted = (cursor.rowcount or 0) > 0
        if deleted:
            self._invalidate_cache()
        return deleted

    async def list_all(
        self,
        *,
        kind: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[BlacklistEntry]:
        """List blacklist entries with optional filtering by kind and query."""
        clauses: list[str] = []
        params: list[object] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if query and query.strip():
            clauses.append(
                "(display_name LIKE ? OR artist_name LIKE ? OR track_title LIKE ?)"
            )
            pattern = f"%{query.strip()}%"
            params.extend([pattern, pattern, pattern])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
        SELECT id, kind, normalized_key, display_name, artist_name, track_title, reason, created_at
        FROM blacklist
        {where}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        rows = await self._sqlite.fetchall(sql, params)
        return tuple(row_to_blacklist(r) for r in rows)

    async def count(self, *, kind: str | None = None) -> int:
        """Return the count of blacklist entries, optionally filtered by kind."""
        if kind:
            row = await self._sqlite.fetchone(
                "SELECT COUNT(*) FROM blacklist WHERE kind = ?", (kind,)
            )
        else:
            row = await self._sqlite.fetchone("SELECT COUNT(*) FROM blacklist")
        return int(row[0]) if row else 0

    async def get_blocked_artist_keys(self) -> frozenset[str]:
        """Return all blocked normalized artist keys in memory for fast lookup."""
        await self._load_cache_if_needed()
        return frozenset(self._blocked_artists or ())

    async def get_blocked_track_keys(self) -> frozenset[str]:
        """Return all blocked normalized track keys ('artist|title') in memory for fast lookup."""
        await self._load_cache_if_needed()
        return frozenset(self._blocked_tracks or ())

    async def is_artist_blocked(self, normalized_artist: str) -> bool:
        """Check whether an artist is blocked."""
        await self._load_cache_if_needed()
        return normalized_artist in (self._blocked_artists or ())

    async def is_track_blocked(self, normalized_track_key: str) -> bool:
        """Check whether a track key ('artist|title') is blocked."""
        await self._load_cache_if_needed()
        return normalized_track_key in (self._blocked_tracks or ())

    async def get_by_key(self, kind: str, normalized_key: str) -> BlacklistEntry | None:
        """Fetch an entry by kind and normalized key."""
        row = await self._sqlite.fetchone(_SELECT_BY_KEY_SQL, (kind, normalized_key))
        return row_to_blacklist(row) if row else None
