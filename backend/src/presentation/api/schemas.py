"""JSON serialization and request bodies for the local web API.

The API speaks plain JSON dicts; these helpers are the only place where domain
entities are flattened for the browser. Request bodies use pydantic because
FastAPI already depends on it — domain entities stay framework-free.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

JobKind = Literal[
    "index",
    "seed-crawl",
    "seed-llm",
    "fetch-metadata",
    "analyze-set",
    "seed-itunes",
    "import-local",
]


# --------------------------------------------------------------- request bodies


class JobRequest(BaseModel):
    """Start one background job with CLI-equivalent parameters."""

    kind: JobKind
    params: dict[str, Any] = Field(default_factory=dict)


class HeardRequest(BaseModel):
    """Two-way heard toggle."""

    heard: bool


class VibeSearchRequest(BaseModel):
    """Natural-language sound description plus absolute filters."""

    query: str
    limit: int = Field(default=30, ge=1, le=500)
    bpm_min: float | None = None
    bpm_max: float | None = None
    camelot_keys: list[str] = Field(default_factory=list)
    exclude_heard: bool = False
    genre: str | None = None


class ResetEmbeddingsRequest(BaseModel):
    """Destructive action guard; the UI confirms before sending."""

    confirm: bool = False


class BlacklistCreateRequest(BaseModel):
    """Payload to add an artist or track to the blacklist."""

    kind: Literal["artist", "track"] = "artist"
    name: str = Field(..., min_length=1)
    track_title: str | None = None
    reason: str | None = None


# ------------------------------------------------------------------ serializers


def track_payload(track: Any, *, heard: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Flatten a :class:`~domain.entities.track.Track` for the browser."""
    preview_url = track.preview_url
    if getattr(track, "local_path", None):
        preview_url = f"/api/catalog/tracks/{track.id}/audio"
    return {
        "id": track.id,
        "title": track.title,
        "artist": track.artist,
        "album": track.album,
        "genre": track.genre,
        "duration_seconds": track.duration_seconds,
        "bpm": track.bpm.value if track.bpm is not None else None,
        "key": track.key.notation if track.key is not None else None,
        "release_year": track.release_year,
        "preview_url": preview_url,
        "artwork_url": track.artwork_url,
        "store_url": track.store_url,
        "source": track.source,
        "local_path": getattr(track, "local_path", None),
        "is_heard": track.id in heard,
    }


def match_payload(match: Any, *, heard: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Flatten a :class:`~domain.entities.dj_set.TrackMatch`."""
    return {
        "track": track_payload(match.track, heard=heard),
        "similarity": match.similarity_percent,
        "is_exact_id": match.is_exact_id,
    }


def passage_payload(
    passage: Any, *, heard: frozenset[str] = frozenset()
) -> dict[str, Any]:
    """Flatten one analyzed DJ-set passage and its candidate matches."""
    time_range = passage.time_range
    return {
        "start_seconds": time_range.start_seconds,
        "end_seconds": time_range.end_seconds,
        "duration_seconds": time_range.duration_seconds,
        "bpm": passage.bpm.value if passage.bpm is not None else None,
        "key": passage.key.notation if passage.key is not None else None,
        "exact_id_match": passage.exact_id_match,
        "exact_id_title": passage.exact_id_title,
        "exact_id_artist": passage.exact_id_artist,
        "exact_id_source": passage.exact_id_source,
        "exact_id_display_name": passage.exact_id_display_name,
        "matches": [
            match_payload(match, heard=heard) for match in passage.closest_matches
        ],
    }


def set_summary_payload(dj_set: Any) -> dict[str, Any]:
    """Flatten a :class:`~domain.entities.dj_set.DJSet` without passages."""
    return {
        "id": dj_set.id,
        "title": dj_set.title,
        "artist": dj_set.artist,
        "source_url": dj_set.source_url,
        "duration_seconds": dj_set.duration_seconds,
        "thumbnail_url": dj_set.thumbnail_url,
        "bpm_min": dj_set.bpm_min.value if dj_set.bpm_min is not None else None,
        "bpm_max": dj_set.bpm_max.value if dj_set.bpm_max is not None else None,
        "passage_count": dj_set.passage_count,
    }


def set_detail_payload(
    dj_set: Any, *, heard: frozenset[str] = frozenset()
) -> dict[str, Any]:
    """Set summary plus its passages in playback order."""
    payload = set_summary_payload(dj_set)
    payload["passages"] = [
        passage_payload(passage, heard=heard) for passage in dj_set.ordered_passages()
    ]
    return payload


def set_match_payload(
    match: Any, *, heard: frozenset[str] = frozenset()
) -> dict[str, Any]:
    """Flatten a :class:`~domain.entities.dj_set.SetMatch`."""
    return {
        "set": set_summary_payload(match.dj_set),
        "similarity": match.similarity_percent,
    }


def hardware_payload(info: Any) -> dict[str, Any]:
    """Flatten a :class:`~domain.value_objects.hardware.HardwareInfo`."""
    return {
        "torch_version": info.torch_version,
        "cuda_available": info.cuda_available,
        "cuda_version": info.cuda_version,
        "gpu_name": info.gpu_name,
        "vram_total_mb": info.vram_total_mb,
        "vram_free_mb": info.vram_free_mb,
        "ram_total_mb": info.ram_total_mb,
        "ram_free_mb": info.ram_free_mb,
        "ffmpeg_path": info.ffmpeg_path,
        "ffmpeg_version": info.ffmpeg_version,
        "gpu_ready": info.gpu_ready,
        "has_ffmpeg": info.has_ffmpeg,
    }


def genre_stat_payload(stat: Any) -> dict[str, Any]:
    return {
        "genre": stat.genre,
        "track_count": stat.track_count,
        "embedded_count": stat.embedded_count,
    }


def bpm_bucket_stat_payload(stat: Any) -> dict[str, Any]:
    return {
        "label": stat.label,
        "track_count": stat.track_count,
    }


def source_stat_payload(stat: Any) -> dict[str, Any]:
    return {
        "source": stat.source,
        "track_count": stat.track_count,
        "embedded_count": stat.embedded_count,
    }


def key_stat_payload(stat: Any) -> dict[str, Any]:
    return {
        "camelot_key": stat.camelot_key,
        "track_count": stat.track_count,
    }


def artist_summary_payload(summary: Any) -> dict[str, Any]:
    return {
        "artist": summary.artist,
        "track_count": summary.track_count,
        "embedded_count": summary.embedded_count,
        "genres": list(summary.genres),
        "sources": list(summary.sources),
        "sample_track_id": summary.sample_track_id,
        "sample_track_title": summary.sample_track_title,
    }


def catalog_analytics_payload(analytics: Any) -> dict[str, Any]:
    return {
        "total_tracks": analytics.total_tracks,
        "total_embedded": analytics.total_embedded,
        "total_artists": analytics.total_artists,
        "total_local": analytics.total_local,
        "total_itunes": analytics.total_itunes,
        "genres": [genre_stat_payload(g) for g in analytics.genres],
        "bpm_buckets": [bpm_bucket_stat_payload(b) for b in analytics.bpm_buckets],
        "sources": [source_stat_payload(s) for s in analytics.sources],
        "top_keys": [key_stat_payload(k) for k in analytics.top_keys],
    }


def blacklist_entry_payload(entry: Any) -> dict[str, Any]:
    return {
        "id": entry.id,
        "kind": entry.kind,
        "normalized_key": entry.normalized_key,
        "display_name": entry.display_name,
        "artist_name": entry.artist_name,
        "track_title": entry.track_title,
        "reason": entry.reason,
        "created_at": entry.created_at,
    }
