"""Mapping between ``Track``, the ``tracks`` table, and LanceDB rows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from domain.entities.track import Track

from ..normalization import normalize_artist_title


def track_to_row(track: Track) -> dict[str, Any]:
    """Return the SQLite column values for a track."""
    return {
        "id": track.id,
        "itunes_track_id": (track.external_id if track.source == "itunes" else None),
        "title": track.title,
        "artist": track.artist,
        "normalized_key": normalize_artist_title(track.artist, track.title),
        "album": track.album,
        "genre": track.genre,
        "duration_sec": track.duration_seconds,
        "release_year": track.release_year,
        "preview_url": track.preview_url,
        "artwork_url": track.artwork_url,
        "store_url": track.store_url,
        "bpm": track.bpm.value if track.bpm is not None else None,
        "camelot_key": track.key.notation if track.key is not None else None,
        "is_embedded": 1 if track.embedding is not None else 0,
        "source": track.source,
        "external_id": track.external_id,
        "isrc": track.isrc,
        "local_path": track.local_path,
    }


def _row_field(row: Mapping[str, Any], key: str) -> Any:
    try:
        return row[key]
    except (IndexError, KeyError):
        return None


def row_to_track(row: Mapping[str, Any]) -> Track:
    """Build a domain track from a SQLite row."""
    external_id = row["external_id"]
    if external_id is None and row["itunes_track_id"] is not None:
        external_id = str(row["itunes_track_id"])
    return Track(
        id=row["id"],
        title=row["title"],
        artist=row["artist"],
        duration_seconds=row["duration_sec"],
        bpm=row["bpm"],
        key=row["camelot_key"],
        genre=row["genre"],
        release_year=row["release_year"],
        isrc=row["isrc"],
        preview_url=row["preview_url"],
        artwork_url=row["artwork_url"],
        album=row["album"],
        store_url=row["store_url"],
        source=row["source"],
        external_id=external_id,
        local_path=_row_field(row, "local_path"),
    )


def track_to_vector_row(track: Track) -> dict[str, Any]:
    """Return the LanceDB row for a track that already has an embedding."""
    if track.embedding is None:
        raise ValueError("track has no embedding")
    return {
        "id": track.id,
        "bpm": track.bpm.value if track.bpm is not None else None,
        "camelot_key": track.key.notation if track.key is not None else None,
        "genre": track.genre,
        "vector": list(track.embedding.values),
    }
