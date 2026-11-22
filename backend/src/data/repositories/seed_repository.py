"""SQLite implementation of ``ISeedRepository``."""

from __future__ import annotations

from collections.abc import Sequence

from domain.entities.track import (
    SEED_CATEGORIES,
    SEED_STATUSES,
    SeedArtist,
    SeedStatus,
)
from domain.interfaces.repositories import IBlacklistRepository, ISeedRepository

from ..datasources.local.sqlite_client import SQLiteClient
from ..mappers.seed_mapper import row_to_seed, seed_to_row
from ..normalization import normalize_artist_key, normalize_seed_name

# No conflict target: either unique constraint may fire (name_normalized or
# the partial index on deezer_id). On a deezer_id collision the existing row
# wins its identity; we only merge metadata and raise priority.
_UPSERT_SQL = """
INSERT INTO seed_artists (
    name, name_normalized, deezer_id, priority_score, category, status, source
)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT DO UPDATE SET
    deezer_id = COALESCE(excluded.deezer_id, seed_artists.deezer_id),
    priority_score = MAX(seed_artists.priority_score, excluded.priority_score),
    category = excluded.category,
    source = excluded.source,
    updated_at = CURRENT_TIMESTAMP
"""

_DISCOVERY_SQL = """
INSERT INTO seed_artists (
    name, name_normalized, deezer_id, priority_score, category, status, source
)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT DO UPDATE SET
    deezer_id = COALESCE(excluded.deezer_id, seed_artists.deezer_id),
    priority_score = MIN(
        1.0,
        MAX(seed_artists.priority_score, excluded.priority_score) + ?
    ),
    category = excluded.category,
    source = excluded.source,
    updated_at = CURRENT_TIMESTAMP
"""


class SQLiteSeedRepository(ISeedRepository):
    """Persist crawl seeds and their priority/status lifecycle."""

    def __init__(
        self,
        sqlite: SQLiteClient,
        blacklist: IBlacklistRepository | None = None,
    ) -> None:
        self._sqlite = sqlite
        self._blacklist = blacklist

    async def upsert_many(self, seeds: Sequence[SeedArtist]) -> int:
        if not seeds:
            return 0
        if self._blacklist is not None:
            blocked = await self._blacklist.get_blocked_artist_keys()
            seeds = [s for s in seeds if normalize_artist_key(s.name) not in blocked]
            if not seeds:
                return 0
        parameters = [
            (
                row["name"],
                row["name_normalized"],
                row["deezer_id"],
                row["priority_score"],
                row["category"],
                row["status"],
                row["source"],
            )
            for row in (seed_to_row(seed) for seed in seeds)
        ]
        await self._sqlite.executemany(_UPSERT_SQL, parameters)
        return len(parameters)

    async def record_discovery(
        self,
        seeds: Sequence[SeedArtist],
        *,
        priority_increment: float = 0.05,
    ) -> int:
        if not 0.0 <= priority_increment <= 1.0:
            raise ValueError("priority_increment must be between 0.0 and 1.0")
        if not seeds:
            return 0
        if self._blacklist is not None:
            blocked = await self._blacklist.get_blocked_artist_keys()
            seeds = [s for s in seeds if normalize_artist_key(s.name) not in blocked]
            if not seeds:
                return 0
        parameters = [
            (
                row["name"],
                row["name_normalized"],
                row["deezer_id"],
                row["priority_score"],
                row["category"],
                row["status"],
                row["source"],
                priority_increment,
            )
            for row in (seed_to_row(seed) for seed in seeds)
        ]
        await self._sqlite.executemany(_DISCOVERY_SQL, parameters)
        return len(parameters)

    async def get_by_name(self, name: str) -> SeedArtist | None:
        row = await self._sqlite.fetchone(
            "SELECT * FROM seed_artists WHERE name_normalized = ?",
            (normalize_seed_name(name),),
        )
        return row_to_seed(row) if row is not None else None

    async def list_by_status(
        self,
        status: SeedStatus,
        limit: int = 100,
    ) -> Sequence[SeedArtist]:
        self._validate_status(status)
        if limit <= 0:
            return ()
        rows = await self._sqlite.fetchall(
            """
            SELECT * FROM seed_artists
            WHERE status = ?
            ORDER BY priority_score DESC, name COLLATE NOCASE ASC
            LIMIT ?
            """,
            (status, limit),
        )
        return tuple(row_to_seed(row) for row in rows)

    async def list_by_source(
        self,
        source: str,
        limit: int = 100,
    ) -> Sequence[SeedArtist]:
        if limit <= 0:
            return ()
        rows = await self._sqlite.fetchall(
            """
            SELECT * FROM seed_artists
            WHERE source = ?
            ORDER BY priority_score DESC, name COLLATE NOCASE ASC
            LIMIT ?
            """,
            (source, limit),
        )
        return tuple(row_to_seed(row) for row in rows)

    async def update_status(self, name: str, status: SeedStatus) -> None:
        self._validate_status(status)
        await self._sqlite.execute(
            """
            UPDATE seed_artists
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE name_normalized = ?
            """,
            (status, normalize_seed_name(name)),
        )

    async def count_by_category(self, category: str) -> int:
        if category not in SEED_CATEGORIES:
            raise ValueError(
                f"category must be one of {sorted(SEED_CATEGORIES)}, got {category!r}"
            )
        row = await self._sqlite.fetchone(
            "SELECT COUNT(*) AS total FROM seed_artists WHERE category = ?",
            (category,),
        )
        return int(row["total"]) if row is not None else 0

    async def count_by_status(self, status: SeedStatus) -> int:
        self._validate_status(status)
        row = await self._sqlite.fetchone(
            "SELECT COUNT(*) AS total FROM seed_artists WHERE status = ?",
            (status,),
        )
        return int(row["total"]) if row is not None else 0

    async def count(self) -> int:
        row = await self._sqlite.fetchone("SELECT COUNT(*) AS total FROM seed_artists")
        return int(row["total"]) if row is not None else 0

    async def delete_by_name(self, name: str) -> bool:
        norm_name = normalize_seed_name(name)
        cursor = await self._sqlite.execute(
            "DELETE FROM seed_artists WHERE name_normalized = ? OR name = ? COLLATE NOCASE",
            (norm_name, name),
        )
        return (cursor.rowcount or 0) > 0

    @staticmethod
    def _validate_status(status: str) -> None:
        if status not in SEED_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(SEED_STATUSES)}, got {status!r}"
            )
