"""Row <-> domain mapping for BlacklistEntry."""

from __future__ import annotations

import sqlite3
from typing import Any

from domain.entities.track import BlacklistEntry


def row_to_blacklist(row: sqlite3.Row | dict[str, Any]) -> BlacklistEntry:
    """Convert an SQLite row into a frozen BlacklistEntry."""
    return BlacklistEntry(
        id=row["id"],
        kind=row["kind"],
        normalized_key=row["normalized_key"],
        display_name=row["display_name"],
        artist_name=row["artist_name"],
        track_title=row["track_title"],
        reason=row["reason"],
        created_at=row["created_at"],
    )
