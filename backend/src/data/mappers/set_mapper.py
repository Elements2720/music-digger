"""Mapping between ``DJSet``/``Passage`` entities and SQLite/LanceDB rows.

Passage embeddings are stored as little-endian float16 BLOBs (1 KB per
512-dim vector) via :mod:`struct` — dense, exact round-trips, and no
third-party imports needed in the mapper.
"""

from __future__ import annotations

import json
import struct
from collections.abc import Mapping, Sequence
from typing import Any

from domain.entities.dj_set import DJSet, Passage, TrackMatch
from domain.entities.track import Track
from domain.value_objects.audio_features import (
    EmbeddingVector,
    TimeRange,
)

_UNKNOWN = "Unknown"
_HALF_FLOAT = "e"  # struct little-endian half-precision code


def embedding_to_blob(embedding: EmbeddingVector) -> bytes:
    """Pack an embedding as little-endian float16 bytes."""
    return struct.pack(f"<{len(embedding.values)}{_HALF_FLOAT}", *embedding.values)


def blob_to_embedding(blob: bytes) -> EmbeddingVector | None:
    """Unpack a float16 BLOB; ``None`` for missing/empty blobs."""
    if not blob:
        return None
    count = len(blob) // struct.calcsize(_HALF_FLOAT)
    values = struct.unpack(f"<{count}{_HALF_FLOAT}", blob[: count * 2])
    return EmbeddingVector(values=values)


def set_to_row(dj_set: DJSet) -> dict[str, Any]:
    """Return the ``dj_sets`` column values for a set."""
    return {
        "id": dj_set.id,
        "title": dj_set.title,
        "source_url": dj_set.source_url,
        "duration_sec": dj_set.duration_seconds,
        "artist": dj_set.artist,
        "thumbnail_url": dj_set.thumbnail_url,
        "bpm_min": dj_set.bpm_min.value if dj_set.bpm_min is not None else None,
        "bpm_max": dj_set.bpm_max.value if dj_set.bpm_max is not None else None,
    }


def row_to_set(row: Mapping[str, Any]) -> DJSet:
    """Build a domain set (without passages) from a SQLite row."""
    return DJSet(
        id=row["id"],
        title=row["title"],
        source_url=row["source_url"],
        duration_seconds=row["duration_sec"],
        artist=row["artist"],
        thumbnail_url=row["thumbnail_url"],
        bpm_min=row["bpm_min"],
        bpm_max=row["bpm_max"],
    )


def passage_to_row(set_id: str, passage: Passage) -> dict[str, Any]:
    """Return the ``set_passages`` column values for one passage."""
    return {
        "set_id": set_id,
        "start_sec": passage.time_range.start_seconds,
        "end_sec": passage.time_range.end_seconds,
        "bpm": passage.bpm.value if passage.bpm is not None else None,
        "camelot_key": passage.key.notation if passage.key is not None else None,
        "exact_id_match": 1 if passage.exact_id_match else 0,
        "exact_id_title": passage.exact_id_title,
        "exact_id_artist": passage.exact_id_artist,
        "exact_id_source": passage.exact_id_source,
        "embedding": (
            embedding_to_blob(passage.embedding)
            if passage.embedding is not None
            else None
        ),
        "closest_matches_json": json.dumps(
            [_match_to_json(match) for match in passage.closest_matches]
        ),
    }


def row_to_passage(row: Mapping[str, Any]) -> Passage:
    """Build a domain passage from a SQLite row."""
    matches = tuple(
        _match_from_json(item) for item in json.loads(row["closest_matches_json"])
    )
    return Passage(
        time_range=TimeRange(row["start_sec"], row["end_sec"]),
        bpm=row["bpm"],
        key=row["camelot_key"],
        exact_id_match=bool(row["exact_id_match"]),
        closest_matches=matches,
        exact_id_title=row["exact_id_title"],
        exact_id_artist=row["exact_id_artist"],
        exact_id_source=row["exact_id_source"],
        embedding=blob_to_embedding(row["embedding"] or b""),
    )


def set_to_vector_row(dj_set: DJSet) -> dict[str, Any]:
    """Return the ``set_vectors`` LanceDB row for an embedded set."""
    if dj_set.embedding is None:
        raise ValueError(f"set {dj_set.id!r} has no embedding")
    return {
        "id": dj_set.id,
        "bpm_min": dj_set.bpm_min.value if dj_set.bpm_min is not None else None,
        "bpm_max": dj_set.bpm_max.value if dj_set.bpm_max is not None else None,
        "vector": list(dj_set.embedding.values),
    }


def _match_to_json(match: TrackMatch) -> dict[str, Any]:
    track = match.track
    return {
        "track_id": track.id,
        "title": track.title,
        "artist": track.artist,
        "bpm": track.bpm.value if track.bpm is not None else None,
        "key": track.key.notation if track.key is not None else None,
        "genre": track.genre,
        "similarity": match.similarity_score,
        "is_exact_id": match.is_exact_id,
    }


def _match_from_json(item: Mapping[str, Any]) -> TrackMatch:
    track = Track(
        id=str(item.get("track_id", _UNKNOWN)),
        title=str(item.get("title") or _UNKNOWN),
        artist=str(item.get("artist") or _UNKNOWN),
        bpm=item.get("bpm"),
        key=item.get("key"),
        genre=item.get("genre"),
    )
    return TrackMatch(
        track=track,
        similarity_score=float(item.get("similarity", 0.0)),
        is_exact_id=bool(item.get("is_exact_id", False)),
    )


def passages_to_rows(set_id: str, passages: Sequence[Passage]) -> list[dict[str, Any]]:
    """Return insert-ready rows for every passage of a set."""
    return [passage_to_row(set_id, passage) for passage in passages]
