"""SQLite implementation of ``IPlannedSetRepository``."""

from __future__ import annotations

from collections.abc import Sequence

from domain.entities.set_plan import PlannedSet
from domain.interfaces.repositories import IPlannedSetRepository

from ..datasources.local.sqlite_client import SQLiteClient


class SQLitePlannedSetRepository(IPlannedSetRepository):
    """Persist and query curated DJ set plans in SQLite."""

    def __init__(self, sqlite: SQLiteClient) -> None:
        self._sqlite = sqlite

    async def save(self, planned_set: PlannedSet) -> PlannedSet:
        """Save a new planned set or update an existing one, preserving track order."""
        if planned_set.id is None:
            cursor = await self._sqlite.execute(
                "INSERT INTO planned_sets (name, created_at, updated_at) "
                "VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (planned_set.name.strip() or "Untitled Set",),
            )
            set_id = int(cursor.lastrowid)
        else:
            set_id = planned_set.id
            await self._sqlite.execute(
                "UPDATE planned_sets SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (planned_set.name.strip() or "Untitled Set", set_id),
            )
            await self._sqlite.execute(
                "DELETE FROM planned_set_tracks WHERE set_id = ?", (set_id,)
            )

        # Insert tracks in order
        if planned_set.track_ids:
            track_rows = [
                (set_id, pos, tid) for pos, tid in enumerate(planned_set.track_ids)
            ]
            await self._sqlite.executemany(
                "INSERT INTO planned_set_tracks (set_id, position, track_id) VALUES (?, ?, ?)",
                track_rows,
            )

        row = await self._sqlite.fetchone(
            "SELECT id, name, created_at, updated_at FROM planned_sets WHERE id = ?",
            (set_id,),
        )
        if row is None:
            return PlannedSet(
                id=set_id,
                name=planned_set.name,
                track_ids=planned_set.track_ids,
            )

        return PlannedSet(
            id=int(row["id"]),
            name=str(row["name"]),
            track_ids=planned_set.track_ids,
            created_at=str(row["created_at"]) if row["created_at"] else None,
            updated_at=str(row["updated_at"]) if row["updated_at"] else None,
        )

    async def get_by_id(self, set_id: int) -> PlannedSet | None:
        """Fetch a planned set by ID along with its ordered track IDs."""
        row = await self._sqlite.fetchone(
            "SELECT id, name, created_at, updated_at FROM planned_sets WHERE id = ?",
            (set_id,),
        )
        if row is None:
            return None

        track_rows = await self._sqlite.fetchall(
            "SELECT track_id FROM planned_set_tracks WHERE set_id = ? ORDER BY position ASC",
            (set_id,),
        )
        track_ids = tuple(str(r["track_id"]) for r in track_rows)

        return PlannedSet(
            id=int(row["id"]),
            name=str(row["name"]),
            track_ids=track_ids,
            created_at=str(row["created_at"]) if row["created_at"] else None,
            updated_at=str(row["updated_at"]) if row["updated_at"] else None,
        )

    async def list_all(self) -> Sequence[PlannedSet]:
        """Return all planned sets ordered by last updated descending."""
        set_rows = await self._sqlite.fetchall(
            "SELECT id, name, created_at, updated_at FROM planned_sets "
            "ORDER BY updated_at DESC, id DESC"
        )
        if not set_rows:
            return ()

        track_rows = await self._sqlite.fetchall(
            "SELECT set_id, track_id FROM planned_set_tracks ORDER BY set_id, position ASC"
        )
        tracks_by_set: dict[int, list[str]] = {}
        for r in track_rows:
            tracks_by_set.setdefault(int(r["set_id"]), []).append(str(r["track_id"]))

        return tuple(
            PlannedSet(
                id=int(r["id"]),
                name=str(r["name"]),
                track_ids=tuple(tracks_by_set.get(int(r["id"]), ())),
                created_at=str(r["created_at"]) if r["created_at"] else None,
                updated_at=str(r["updated_at"]) if r["updated_at"] else None,
            )
            for r in set_rows
        )

    async def delete(self, set_id: int) -> bool:
        """Delete a planned set by ID."""
        await self._sqlite.execute(
            "DELETE FROM planned_set_tracks WHERE set_id = ?", (set_id,)
        )
        cursor = await self._sqlite.execute(
            "DELETE FROM planned_sets WHERE id = ?", (set_id,)
        )
        return bool(cursor.rowcount and cursor.rowcount > 0)
