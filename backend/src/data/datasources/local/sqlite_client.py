"""Async SQLite connection and schema management.

The database is a single local file (``storage/app.db`` by default). WAL mode
lets the CLI and a future API process read while a metadata batch is writing,
without ever loading the catalog into memory.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS seed_artists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_normalized TEXT NOT NULL UNIQUE,
    deezer_id TEXT,
    priority_score REAL NOT NULL DEFAULT 0.0
        CHECK (priority_score >= 0.0 AND priority_score <= 1.0),
    category TEXT NOT NULL
        CHECK (category IN ('electronic', 'general')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'fetched', 'failed')),
    source TEXT NOT NULL DEFAULT 'unknown',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_seed_artists_deezer_id
    ON seed_artists(deezer_id) WHERE deezer_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_seed_artists_status_priority
    ON seed_artists(status, priority_score DESC);

CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    itunes_track_id TEXT UNIQUE,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    normalized_key TEXT NOT NULL UNIQUE,
    album TEXT,
    genre TEXT,
    duration_sec REAL,
    release_year INTEGER,
    preview_url TEXT,
    artwork_url TEXT,
    store_url TEXT,
    bpm REAL,
    camelot_key TEXT,
    is_embedded INTEGER NOT NULL DEFAULT 0
        CHECK (is_embedded IN (0, 1)),
    is_heard INTEGER NOT NULL DEFAULT 0
        CHECK (is_heard IN (0, 1)),
    index_failures INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'itunes',
    external_id TEXT,
    isrc TEXT,
    local_path TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tracks_external_id
    ON tracks(source, external_id);
CREATE INDEX IF NOT EXISTS idx_tracks_bpm ON tracks(bpm);
CREATE INDEX IF NOT EXISTS idx_tracks_genre ON tracks(genre);
CREATE INDEX IF NOT EXISTS idx_tracks_heard ON tracks(is_heard);

CREATE TABLE IF NOT EXISTS dj_sets (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_url TEXT,
    duration_sec REAL,
    artist TEXT,
    thumbnail_url TEXT,
    bpm_min REAL,
    bpm_max REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS set_passages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    set_id TEXT NOT NULL REFERENCES dj_sets(id) ON DELETE CASCADE,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    bpm REAL,
    camelot_key TEXT,
    exact_id_match INTEGER NOT NULL DEFAULT 0
        CHECK (exact_id_match IN (0, 1)),
    exact_id_title TEXT,
    exact_id_artist TEXT,
    exact_id_source TEXT,
    embedding BLOB,
    closest_matches_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE (set_id, start_sec, end_sec)
);

CREATE INDEX IF NOT EXISTS idx_set_passages_set_id
    ON set_passages(set_id, start_sec);

CREATE TABLE IF NOT EXISTS blacklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL
        CHECK (kind IN ('artist', 'track')),
    normalized_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    artist_name TEXT,
    track_title TEXT,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(kind, normalized_key)
);

CREATE INDEX IF NOT EXISTS idx_blacklist_kind
    ON blacklist(kind);
CREATE INDEX IF NOT EXISTS idx_blacklist_normalized_key
    ON blacklist(normalized_key);

"""


_TRACK_COLUMN_MIGRATIONS: tuple[tuple[str, str], ...] = (
    # (column, DDL) — columns referenced by SCHEMA indexes or Phase 3 code
    # that pre-Phase-2/3 databases may lack. NOT NULL requires a DEFAULT.
    ("source", "TEXT NOT NULL DEFAULT 'itunes'"),
    ("external_id", "TEXT"),
    ("index_failures", "INTEGER NOT NULL DEFAULT 0"),
    ("local_path", "TEXT"),
)

# Phase 4 set-analysis columns for databases created before Phase 4.
_DJ_SET_COLUMN_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("artist", "TEXT"),
    ("thumbnail_url", "TEXT"),
    ("bpm_min", "REAL"),
    ("bpm_max", "REAL"),
)

_SET_PASSAGE_COLUMN_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("exact_id_title", "TEXT"),
    ("exact_id_artist", "TEXT"),
    ("exact_id_source", "TEXT"),
    ("embedding", "BLOB"),
)


async def _migrate(connection: aiosqlite.Connection) -> None:
    """Apply additive migrations for databases created by earlier phases."""
    migrations: dict[str, tuple[tuple[str, str], ...]] = {
        "tracks": _TRACK_COLUMN_MIGRATIONS,
        "dj_sets": _DJ_SET_COLUMN_MIGRATIONS,
        "set_passages": _SET_PASSAGE_COLUMN_MIGRATIONS,
    }
    migrated_any = False
    for table, columns in migrations.items():
        async with connection.execute(f"PRAGMA table_info({table})") as cursor:
            existing = {row[1] for row in await cursor.fetchall()}
        if not existing:
            continue  # fresh table; the schema script creates everything
        for name, ddl in columns:
            if name not in existing:
                await connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                migrated_any = True

    # Ensure blacklist table enforces composite UNIQUE(kind, normalized_key)
    async with connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='blacklist'"
    ) as cursor:
        bl_row = await cursor.fetchone()
    if bl_row and bl_row[0] and "UNIQUE(kind, normalized_key)" not in bl_row[0]:
        await connection.execute("PRAGMA foreign_keys = OFF")
        await connection.execute("""
            CREATE TABLE blacklist_migrated (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL CHECK (kind IN ('artist', 'track')),
                normalized_key TEXT NOT NULL,
                display_name TEXT NOT NULL,
                artist_name TEXT,
                track_title TEXT,
                reason TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(kind, normalized_key)
            )
        """)
        await connection.execute("""
            INSERT OR IGNORE INTO blacklist_migrated (
                id, kind, normalized_key, display_name, artist_name, track_title, reason, created_at
            )
            SELECT id, kind, normalized_key, display_name, artist_name, track_title, reason, created_at
            FROM blacklist
        """)
        await connection.execute("DROP TABLE blacklist")
        await connection.execute("ALTER TABLE blacklist_migrated RENAME TO blacklist")
        await connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_blacklist_kind ON blacklist(kind)"
        )
        await connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_blacklist_normalized_key ON blacklist(normalized_key)"
        )
        await connection.execute("PRAGMA foreign_keys = ON")
        migrated_any = True

    if migrated_any:
        await connection.commit()


class SQLiteClient:
    """Thin async wrapper around one ``aiosqlite`` connection.

    A single connection is intentional: SQLite serializes writes anyway, and a
    single WAL connection keeps the CLI deterministic. Callers must use the
    connection yielded by :meth:`transaction` for statements inside a
    transaction; calling the client's own ``execute`` methods there would wait
    on the same lock.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)
        self._connection: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        """Filesystem path of the SQLite database."""
        return self._path

    @property
    def connection(self) -> aiosqlite.Connection:
        """Return the live connection, raising when not connected."""
        if self._connection is None:
            raise RuntimeError("SQLiteClient is not connected")
        return self._connection

    async def connect(self) -> None:
        """Open the database, enable WAL, and create missing tables."""
        if self._connection is not None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = await aiosqlite.connect(str(self._path))
        connection.row_factory = aiosqlite.Row
        self._connection = connection
        await connection.execute("PRAGMA journal_mode=WAL")
        await connection.execute("PRAGMA foreign_keys=ON")
        await connection.execute("PRAGMA busy_timeout=5000")
        await connection.execute("PRAGMA synchronous=NORMAL")
        # Migrate BEFORE the schema script: SCHEMA creates indexes that
        # reference columns (e.g. `source`) which a Phase 2 database may lack.
        await _migrate(connection)
        await connection.executescript(SCHEMA)
        await connection.commit()

    async def close(self) -> None:
        """Close the connection."""
        if self._connection is None:
            return
        await self._connection.close()
        self._connection = None

    async def execute(
        self,
        sql: str,
        parameters: Sequence[Any] = (),
    ) -> aiosqlite.Cursor:
        """Execute one statement and commit."""
        async with self._lock:
            cursor = await self.connection.execute(sql, tuple(parameters))
            await self.connection.commit()
            return cursor

    async def executemany(
        self,
        sql: str,
        parameters: Sequence[Sequence[Any]],
    ) -> aiosqlite.Cursor:
        """Execute one statement for many parameter rows and commit."""
        async with self._lock:
            cursor = await self.connection.executemany(sql, parameters)
            await self.connection.commit()
            return cursor

    async def fetchone(
        self,
        sql: str,
        parameters: Sequence[Any] = (),
    ) -> aiosqlite.Row | None:
        """Return the first row, if any."""
        async with (
            self._lock,
            self.connection.execute(sql, tuple(parameters)) as cursor,
        ):
            return await cursor.fetchone()

    async def fetchall(
        self,
        sql: str,
        parameters: Sequence[Any] = (),
    ) -> list[aiosqlite.Row]:
        """Return every row."""
        async with (
            self._lock,
            self.connection.execute(sql, tuple(parameters)) as cursor,
        ):
            return list(await cursor.fetchall())

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        """Run a group of statements atomically on the raw connection."""
        async with self._lock:
            connection = self.connection
            try:
                yield connection
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
