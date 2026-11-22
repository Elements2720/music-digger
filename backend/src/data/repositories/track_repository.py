"""Hybrid track repository: SQLite metadata plus LanceDB vectors."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from domain.entities.analytics import (
    ArtistSummary,
    BpmBucketStat,
    CatalogAnalytics,
    GenreStat,
    KeyStat,
    SourceStat,
)
from domain.entities.dj_set import TrackMatch
from domain.entities.search import SearchFilter
from domain.entities.track import Track
from domain.interfaces.repositories import IBlacklistRepository, ITrackRepository
from domain.value_objects.audio_features import EmbeddingVector

from ..datasources.local.lancedb_client import LanceDBClient
from ..datasources.local.sqlite_client import SQLiteClient
from ..mappers.track_mapper import row_to_track, track_to_row, track_to_vector_row
from ..normalization import (
    normalize_artist_key,
    normalize_text,
    normalize_track_key,
)

_UPSERT_SQL = """
INSERT INTO tracks (
    id, itunes_track_id, title, artist, normalized_key, album, genre,
    duration_sec, release_year, preview_url, artwork_url, store_url, bpm,
    camelot_key, is_embedded, is_heard, source, external_id, isrc, local_path
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
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
    local_path = COALESCE(excluded.local_path, tracks.local_path),
    updated_at = CURRENT_TIMESTAMP
"""


class HybridTrackRepository(ITrackRepository):
    """Coordinate relational metadata with the disk-backed vector index."""

    def __init__(
        self,
        sqlite: SQLiteClient,
        vectors: LanceDBClient,
        blacklist: IBlacklistRepository | None = None,
    ) -> None:
        self._sqlite = sqlite
        self._vectors = vectors
        self._blacklist = blacklist
        self._taste_scores_cache: tuple[dict[str, float], int] | None = None
        self._taste_scores_timestamp: float = 0.0

    def _invalidate_taste_cache(self) -> None:
        self._taste_scores_cache = None
        self._taste_scores_timestamp = 0.0

    async def upsert_many(self, tracks: Sequence[Track]) -> int:
        if not tracks:
            return 0

        if self._blacklist is not None:
            blocked_artists = await self._blacklist.get_blocked_artist_keys()
            blocked_tracks = await self._blacklist.get_blocked_track_keys()
            if blocked_artists or blocked_tracks:
                filtered_tracks: list[Track] = []
                for track in tracks:
                    norm_artist = normalize_artist_key(track.artist)
                    norm_track = normalize_track_key(track.artist, track.title)
                    if norm_artist in blocked_artists or norm_track in blocked_tracks:
                        continue
                    filtered_tracks.append(track)
                tracks = tuple(filtered_tracks)
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
        self._invalidate_taste_cache()
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
        needs_post_filter = bool(
            search_filter.min_year is not None
            or search_filter.max_year is not None
            or search_filter.genres
            or search_filter.exclude_heard
        )
        vector_limit = (
            min(1000, max(search_filter.limit * 8, 200))
            if needs_post_filter
            else search_filter.limit
        )
        vector_matches = await self._vectors.search(
            embedding.values,
            limit=vector_limit,
            where=where,
        )
        tracks = await self.get_many([match.track_id for match in vector_matches])
        by_id = {track.id: track for track in tracks}
        matches: list[TrackMatch] = []
        for vector_match in vector_matches:
            track = by_id.get(vector_match.track_id)
            if track is None:
                continue
            if not search_filter.matches(track, heard_ids):
                continue
            matches.append(
                TrackMatch(
                    track=track,
                    similarity_score=vector_match.similarity,
                )
            )
            if len(matches) >= search_filter.limit:
                break
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
        if search_filter.min_year is not None:
            clauses.append("release_year >= ?")
            parameters.append(search_filter.min_year)
        if search_filter.max_year is not None:
            clauses.append("release_year <= ?")
            parameters.append(search_filter.max_year)
        if search_filter.genres:
            genre_or_clauses = ["genre LIKE ?" for _ in search_filter.genres]
            clauses.append(f"({' OR '.join(genre_or_clauses)})")
            parameters.extend(f"%{g}%" for g in search_filter.genres)
        elif search_filter.genre_filter is not None:
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

    async def search_tracks(self, query: str, limit: int = 30) -> Sequence[Track]:
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

    async def get_embedded_ids(self, track_ids: Sequence[str]) -> frozenset[str]:
        if not track_ids:
            return frozenset()
        placeholders = ", ".join("?" for _ in track_ids)
        rows = await self._sqlite.fetchall(
            f"SELECT id FROM tracks WHERE id IN ({placeholders}) AND is_embedded = 1",
            tuple(track_ids),
        )
        return frozenset(row["id"] for row in rows)

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
        self._invalidate_taste_cache()
        return cleared

    async def delete_by_ids(self, track_ids: Sequence[str]) -> int:
        """Delete tracks from SQLite and LanceDB by their IDs.

        Never deletes user audio files on disk (only DB rows).
        """
        if not track_ids:
            return 0
        total_deleted = 0
        batch_size = 500
        for i in range(0, len(track_ids), batch_size):
            chunk = track_ids[i : i + batch_size]
            placeholders = ", ".join("?" for _ in chunk)
            cursor = await self._sqlite.execute(
                f"DELETE FROM tracks WHERE id IN ({placeholders})",
                tuple(chunk),
            )
            total_deleted += cursor.rowcount or 0
        await self._vectors.delete_ids(track_ids)
        self._invalidate_taste_cache()
        return total_deleted

    async def delete_by_artist(self, artist_name: str) -> tuple[int, tuple[str, ...]]:
        """Delete all tracks by artist name, returning (count_deleted, deleted_ids)."""
        norm_artist = normalize_text(artist_name)
        pattern = f"{norm_artist}|%"
        rows = await self._sqlite.fetchall(
            "SELECT id FROM tracks WHERE artist = ? COLLATE NOCASE OR normalized_key LIKE ?",
            (artist_name, pattern),
        )
        if not rows:
            return (0, ())
        track_ids = tuple(str(row["id"]) for row in rows)
        count = await self.delete_by_ids(track_ids)
        return (count, track_ids)

    async def list_by_artist(
        self, artist_name: str, *, limit: int = 200, offset: int = 0
    ) -> Sequence[Track]:
        """List tracks by artist name."""
        if limit <= 0:
            return ()
        norm_artist = normalize_text(artist_name)
        pattern = f"{norm_artist}|%"
        rows = await self._sqlite.fetchall(
            """
            SELECT * FROM tracks
            WHERE artist = ? COLLATE NOCASE OR normalized_key LIKE ?
            ORDER BY release_year DESC, title COLLATE NOCASE
            LIMIT ? OFFSET ?
            """,
            (artist_name, pattern, limit, offset),
        )
        return tuple(row_to_track(row) for row in rows)

    async def get_artist_taste_scores(self) -> tuple[dict[str, float], int]:
        """Compute mean taste match percentage per artist against local library profile."""
        now = time.monotonic()
        if (
            self._taste_scores_cache is not None
            and (now - self._taste_scores_timestamp) < 300.0
        ):
            return self._taste_scores_cache

        local_rows = await self._sqlite.fetchall(
            "SELECT id FROM tracks WHERE source = 'local' AND is_embedded = 1"
        )
        if not local_rows:
            self._taste_scores_cache = ({}, 0)
            self._taste_scores_timestamp = now
            return ({}, 0)

        seed_ids = [str(r["id"]) for r in local_rows]
        track_scores = await self._vectors.compute_similarity_to_seed_ids(seed_ids)
        if not track_scores:
            self._taste_scores_cache = ({}, len(seed_ids))
            self._taste_scores_timestamp = now
            return ({}, len(seed_ids))

        artist_rows = await self._sqlite.fetchall(
            "SELECT id, artist FROM tracks WHERE is_embedded = 1"
        )
        artist_scores_accum: dict[str, list[float]] = {}
        for r in artist_rows:
            tid = str(r["id"])
            artist = str(r["artist"])
            if tid in track_scores:
                artist_scores_accum.setdefault(artist, []).append(track_scores[tid])

        artist_taste_scores: dict[str, float] = {}
        for artist, scores in artist_scores_accum.items():
            if scores:
                artist_taste_scores[artist] = round(sum(scores) / len(scores), 1)

        result = (artist_taste_scores, len(seed_ids))
        self._taste_scores_cache = result
        self._taste_scores_timestamp = now
        return result

    async def list_artists_summary(
        self,
        *,
        query: str | None = None,
        genre: str | None = None,
        source: str | None = None,
        min_year: int | None = None,
        sort: str = "tracks_desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[ArtistSummary], int]:
        """List artists summary with counts and genres, returning (artists, total_count)."""
        clauses: list[str] = []
        params: list[Any] = []
        if query and query.strip():
            clauses.append("artist LIKE ?")
            params.append(f"%{query.strip()}%")
        if genre and genre.strip():
            clauses.append("LOWER(genre) = LOWER(?)")
            params.append(genre.strip())
        if source and source.strip():
            clauses.append("source = ?")
            params.append(source.strip())
        if min_year is not None:
            clauses.append("release_year >= ?")
            params.append(min_year)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        count_sql = f"SELECT COUNT(DISTINCT artist) AS total FROM tracks {where}"
        count_row = await self._sqlite.fetchone(count_sql, tuple(params))
        total_artists = int(count_row["total"]) if count_row is not None else 0
        if total_artists == 0 or limit <= 0:
            return ((), total_artists)

        taste_scores, _ = await self.get_artist_taste_scores()
        is_taste_sort = sort in ("taste_desc", "taste_asc")

        if sort == "artist_asc":
            order_by = "artist COLLATE NOCASE ASC"
        elif sort == "embedded_desc":
            order_by = (
                "embedded_count DESC, track_count DESC, artist COLLATE NOCASE ASC"
            )
        else:  # "tracks_desc" or taste sort baseline
            order_by = (
                "track_count DESC, embedded_count DESC, artist COLLATE NOCASE ASC"
            )

        if is_taste_sort:
            summary_sql = f"""
            SELECT
                artist,
                COUNT(*) AS track_count,
                SUM(is_embedded) AS embedded_count,
                MIN(release_year) AS year_min,
                MAX(release_year) AS year_max,
                GROUP_CONCAT(DISTINCT genre) AS genres_concat,
                GROUP_CONCAT(DISTINCT source) AS sources_concat,
                MIN(id) AS sample_id,
                MIN(title) AS sample_title
            FROM tracks
            {where}
            GROUP BY artist
            ORDER BY {order_by}
            """
            rows = await self._sqlite.fetchall(summary_sql, tuple(params))
        else:
            summary_sql = f"""
            SELECT
                artist,
                COUNT(*) AS track_count,
                SUM(is_embedded) AS embedded_count,
                MIN(release_year) AS year_min,
                MAX(release_year) AS year_max,
                GROUP_CONCAT(DISTINCT genre) AS genres_concat,
                GROUP_CONCAT(DISTINCT source) AS sources_concat,
                MIN(id) AS sample_id,
                MIN(title) AS sample_title
            FROM tracks
            {where}
            GROUP BY artist
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
            """
            fetch_params = list(params)
            fetch_params.extend([limit, offset])
            rows = await self._sqlite.fetchall(summary_sql, tuple(fetch_params))

        summaries: list[ArtistSummary] = []
        for row in rows:
            genres_raw = row["genres_concat"] or ""
            genres = tuple(g for g in genres_raw.split(",") if g)
            sources_raw = row["sources_concat"] or ""
            sources = tuple(s for s in sources_raw.split(",") if s)
            artist_name = str(row["artist"])
            taste_pct = taste_scores.get(artist_name)
            summaries.append(
                ArtistSummary(
                    artist=artist_name,
                    track_count=int(row["track_count"] or 0),
                    embedded_count=int(row["embedded_count"] or 0),
                    genres=genres,
                    sources=sources,
                    sample_track_id=str(row["sample_id"]) if row["sample_id"] else None,
                    sample_track_title=str(row["sample_title"])
                    if row["sample_title"]
                    else None,
                    year_min=int(row["year_min"])
                    if row["year_min"] is not None
                    else None,
                    year_max=int(row["year_max"])
                    if row["year_max"] is not None
                    else None,
                    taste_match_percent=taste_pct,
                )
            )

        if is_taste_sort:
            if sort == "taste_desc":
                summaries.sort(
                    key=lambda s: (
                        s.taste_match_percent is not None,
                        s.taste_match_percent or 0.0,
                        s.track_count,
                    ),
                    reverse=True,
                )
            elif sort == "taste_asc":
                summaries.sort(
                    key=lambda s: (
                        s.taste_match_percent is not None,
                        -(
                            s.taste_match_percent
                            if s.taste_match_percent is not None
                            else 999.0
                        ),
                        s.track_count,
                    ),
                    reverse=True,
                )
            summaries = summaries[offset : offset + limit]

        return (tuple(summaries), total_artists)

    async def get_catalog_analytics(self) -> CatalogAnalytics:
        """Return high-level analytics and distributions across the catalog."""
        row = await self._sqlite.fetchone(
            """
            SELECT
                COUNT(*) AS total_tracks,
                SUM(is_embedded) AS total_embedded,
                COUNT(DISTINCT artist) AS total_artists,
                SUM(CASE WHEN source = 'local' THEN 1 ELSE 0 END) AS total_local,
                SUM(CASE WHEN source = 'itunes' THEN 1 ELSE 0 END) AS total_itunes
            FROM tracks
            """
        )
        total_tracks = int(row["total_tracks"] or 0) if row else 0
        total_embedded = int(row["total_embedded"] or 0) if row else 0
        total_artists = int(row["total_artists"] or 0) if row else 0
        total_local = int(row["total_local"] or 0) if row else 0
        total_itunes = int(row["total_itunes"] or 0) if row else 0

        genre_rows = await self._sqlite.fetchall(
            """
            SELECT genre, COUNT(*) AS track_count, SUM(is_embedded) AS embedded_count
            FROM tracks
            WHERE genre IS NOT NULL AND TRIM(genre) != ''
            GROUP BY genre
            ORDER BY track_count DESC
            LIMIT 20
            """
        )
        genres = tuple(
            GenreStat(
                genre=str(r["genre"]),
                track_count=int(r["track_count"] or 0),
                embedded_count=int(r["embedded_count"] or 0),
            )
            for r in genre_rows
        )

        bpm_rows = await self._sqlite.fetchall(
            """
            SELECT
                CASE
                    WHEN bpm IS NULL THEN 'Unknown'
                    WHEN bpm < 120 THEN '< 120'
                    WHEN bpm >= 120 AND bpm < 125 THEN '120-124'
                    WHEN bpm >= 125 AND bpm < 130 THEN '125-129'
                    WHEN bpm >= 130 AND bpm < 135 THEN '130-134'
                    WHEN bpm >= 135 AND bpm < 140 THEN '135-139'
                    ELSE '140+'
                END AS bucket_label,
                COUNT(*) AS track_count
            FROM tracks
            GROUP BY bucket_label
            """
        )
        bpm_map = {str(r["bucket_label"]): int(r["track_count"] or 0) for r in bpm_rows}
        bucket_order = [
            "< 120",
            "120-124",
            "125-129",
            "130-134",
            "135-139",
            "140+",
            "Unknown",
        ]
        bpm_buckets = tuple(
            BpmBucketStat(label=lbl, track_count=bpm_map.get(lbl, 0))
            for lbl in bucket_order
            if lbl in bpm_map or total_tracks > 0
        )

        source_rows = await self._sqlite.fetchall(
            """
            SELECT source, COUNT(*) AS track_count, SUM(is_embedded) AS embedded_count
            FROM tracks
            GROUP BY source
            ORDER BY track_count DESC
            """
        )
        sources = tuple(
            SourceStat(
                source=str(r["source"]),
                track_count=int(r["track_count"] or 0),
                embedded_count=int(r["embedded_count"] or 0),
            )
            for r in source_rows
        )

        key_rows = await self._sqlite.fetchall(
            """
            SELECT camelot_key, COUNT(*) AS track_count
            FROM tracks
            WHERE camelot_key IS NOT NULL AND TRIM(camelot_key) != ''
            GROUP BY camelot_key
            ORDER BY track_count DESC
            LIMIT 24
            """
        )
        top_keys = tuple(
            KeyStat(
                camelot_key=str(r["camelot_key"]),
                track_count=int(r["track_count"] or 0),
            )
            for r in key_rows
        )

        return CatalogAnalytics(
            total_tracks=total_tracks,
            total_embedded=total_embedded,
            total_artists=total_artists,
            total_local=total_local,
            total_itunes=total_itunes,
            local_taste_count=total_local,
            genres=genres,
            bpm_buckets=bpm_buckets,
            sources=sources,
            top_keys=top_keys,
        )

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
            row.get("local_path"),
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
