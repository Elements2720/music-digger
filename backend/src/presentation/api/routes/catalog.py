"""Catalog endpoints: stats, search, dig, vibe search, and heard state."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Final, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from data.normalization import normalize_artist_key
from domain.entities.analytics import SimilarArtistMatch
from domain.entities.search import SearchFilter
from domain.entities.track import SeedArtist
from domain.genres import ELECTRONIC_ALLOWED_GENRE_TOKENS, TECHNO_SUBGENRE_PRESETS
from domain.use_cases import (
    BulkCleanupCriteria,
    TrackNotEmbeddedError,
    TrackNotFoundError,
)

from ..schemas import (
    BlacklistCreateRequest,
    BulkCleanupCriteriaRequest,
    BulkCleanupExecuteRequest,
    BulkDeleteArtistsRequest,
    HeardRequest,
    ResetEmbeddingsRequest,
    SeedPurgeRequest,
    VibeSearchRequest,
    artist_summary_payload,
    blacklist_entry_payload,
    bulk_delete_artists_result_payload,
    catalog_analytics_payload,
    liked_artist_payload,
    match_payload,
    seed_breakdown_payload,
    seed_payload,
    similar_artist_payload,
    track_payload,
)
from . import get_container

router = APIRouter(prefix="/api", tags=["catalog"])
LOGGER = logging.getLogger(__name__)


@router.get("/stats")
async def stats(container: Any = Depends(get_container)) -> dict[str, Any]:
    """Seed, track, and DJ-set counts (the CLI ``dig stats``)."""
    seeds = container.seed_repository
    tracks = container.track_repository
    return {
        "seeds": {
            "total": await seeds.count(),
            "pending": await seeds.count_by_status("pending"),
            "fetched": await seeds.count_by_status("fetched"),
            "failed": await seeds.count_by_status("failed"),
            "electronic": await seeds.count_by_category("electronic"),
            "general": await seeds.count_by_category("general"),
        },
        "tracks": {
            "total": await tracks.count(),
            "embedded": await tracks.count_embedded(),
        },
        "sets": {
            "total": await container.set_repository.count(),
        },
    }


@router.get("/tracks/search")
async def search_tracks(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(30, ge=1, le=30),
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Case-insensitive title/artist search, capped at 30 rows."""
    tracks = await container.track_repository.search_tracks(q, limit)
    heard = await container.track_repository.get_heard_ids()
    return {
        "tracks": [track_payload(track, heard=heard) for track in tracks],
        "query": q,
    }


@router.get("/catalog/filter")
async def filter_catalog(
    q: str | None = Query(None, max_length=200),
    key: str | None = Query(None, description="Exact Camelot key, e.g. 12A"),
    bpm_min: float | None = Query(None, ge=0),
    bpm_max: float | None = Query(None, ge=0),
    source: str | None = Query(None, description="local or remote"),
    limit: int = Query(60, ge=1, le=500),
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Exact-metadata catalog filter (Camelot key, BPM range, local/remote).

    Used by the Dig ``VIBE & CATALOG`` panel; unlike vibe search this never
    touches CLAP text embeddings.
    """
    keys = (key.strip(),) if key and key.strip() else ()
    try:
        search_filter = SearchFilter(
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            camelot_keys=keys,
            genre_filter=q.strip() if q and q.strip() else None,
            limit=limit,
        )
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err

    tracks = await container.track_repository.find_by_filter(search_filter)
    heard = await container.track_repository.get_heard_ids()
    if source == "local":
        tracks = [t for t in tracks if t.local_path]
    elif source == "remote":
        tracks = [t for t in tracks if not t.local_path]
    return {"tracks": [track_payload(t, heard=heard) for t in tracks]}


@router.get("/tracks/recent")
async def recent_tracks(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Recently embedded tracks for the Dig picker."""
    tracks = await container.track_repository.list_embedded(
        limit, offset=offset, features_first=True
    )
    heard = await container.track_repository.get_heard_ids()
    return {
        "tracks": [track_payload(track, heard=heard) for track in tracks],
        "embedded_total": await container.track_repository.count_embedded(),
    }


@router.get("/catalog/genre-presets")
@router.get("/genre-presets")
async def get_genre_presets() -> dict[str, Any]:
    """Curated Techno subgenre presets and electronic tokens."""
    return {
        "presets": list(TECHNO_SUBGENRE_PRESETS),
        "electronic_tokens": sorted(ELECTRONIC_ALLOWED_GENRE_TOKENS),
    }


@router.get("/dig/{track_id}")
async def dig(
    track_id: str,
    limit: int = Query(10, ge=1, le=500),
    bpm_tolerance: float | None = Query(None, ge=0),
    harmonic: bool = Query(False),
    harmonic_mode: Literal["strict", "energy_boost"] = Query("strict"),
    max_per_artist: int = Query(0, ge=0, le=50),
    genre: str | None = Query(None),
    genres: str | None = Query(None),
    min_year: int | None = Query(None, ge=1900, le=2100),
    max_year: int | None = Query(None, ge=1900, le=2100),
    exclude_heard: bool = Query(False),
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Track-to-track similarity search (the CLI ``dig dig``)."""
    genres_tuple = (
        tuple(g.strip() for g in genres.split(",") if g.strip()) if genres else ()
    )
    search_filter = SearchFilter(
        limit=limit,
        genre_filter=genre,
        genres=genres_tuple,
        min_year=min_year,
        max_year=max_year,
        exclude_heard=exclude_heard,
    )
    try:
        result = await container.dig_similar_tracks.execute(
            track_id,
            search_filter,
            bpm_tolerance=bpm_tolerance,
            harmonic=harmonic,
            harmonic_mode=harmonic_mode,
            max_per_artist=max_per_artist,
        )
    except TrackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TrackNotEmbeddedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    heard = await container.track_repository.get_heard_ids()
    return {
        "reference": track_payload(result.reference, heard=heard),
        "matches": [match_payload(match, heard=heard) for match in result.matches],
    }


@router.post("/vibe-search")
async def vibe_search(
    payload: VibeSearchRequest,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Text-to-audio search: ``"dark hypnotic peak-time techno"``."""
    try:
        search_filter = SearchFilter(
            limit=payload.limit,
            bpm_min=payload.bpm_min,
            bpm_max=payload.bpm_max,
            camelot_keys=tuple(payload.camelot_keys),
            genre_filter=payload.genre,
            exclude_heard=payload.exclude_heard,
        )
        matches = await container.vibe_search.execute(payload.query, search_filter)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    heard = await container.track_repository.get_heard_ids()
    return {
        "query": payload.query,
        "matches": [match_payload(match, heard=heard) for match in matches],
    }


@router.patch("/tracks/{track_id}/heard")
async def set_heard(
    track_id: str,
    payload: HeardRequest,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Two-way heard toggle (un-hearing is allowed)."""
    track = await container.track_repository.get_by_id(track_id)
    if track is None:
        raise HTTPException(status_code=404, detail=f"track {track_id!r} not found")
    await container.track_repository.set_heard(track_id, payload.heard)
    return {"id": track_id, "is_heard": payload.heard}


@router.post("/reset-embeddings")
async def reset_embeddings(
    payload: ResetEmbeddingsRequest,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Drop every stored embedding after an explicit confirmation."""
    if not payload.confirm:
        raise HTTPException(
            status_code=400, detail='send {"confirm": true} to drop embeddings'
        )
    cleared = await container.track_repository.reset_embeddings()
    return {"cleared": cleared}


AUDIO_MEDIA_TYPES: Final[dict[str, str]] = {
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".aac": "audio/aac",
    ".aif": "audio/x-aiff",
    ".aiff": "audio/x-aiff",
}


@router.get("/catalog/tracks/{track_id}/audio")
@router.get("/tracks/{track_id}/audio")
async def get_track_audio(
    track_id: str,
    container: Any = Depends(get_container),
) -> FileResponse:
    """Stream a local audio file safely."""
    track = await container.track_repository.get_by_id(track_id)
    if track is None or not getattr(track, "local_path", None):
        raise HTTPException(
            status_code=404, detail=f"Local track {track_id!r} not found"
        )
    file_path = Path(track.local_path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Audio file does not exist on disk")
    media_type = AUDIO_MEDIA_TYPES.get(
        file_path.suffix.lower(), "application/octet-stream"
    )
    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type=media_type,
    )


@router.post("/catalog/tracks/{track_id}/download")
@router.post("/tracks/{track_id}/download")
async def download_track(
    track_id: str,
    force: bool = Query(False),
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Download single track audio and persist local_path."""
    try:
        await container.download_tracks.download_one(track_id, force=force)
    except ValueError as exc:
        LOGGER.warning("Track not found for download: %s", track_id)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        LOGGER.exception("Download failed for track %s", track_id)
        raise HTTPException(status_code=502, detail=f"Download failed: {exc}") from exc

    track = await container.track_repository.get_by_id(track_id)
    if track is None:
        raise HTTPException(
            status_code=404, detail=f"Track {track_id!r} not found after download"
        )
    heard = await container.track_repository.get_heard_ids()
    return track_payload(track, heard=heard)


@router.get("/catalog/analytics")
async def get_catalog_analytics(
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Catalog distributions and KPI statistics."""
    analytics = await container.track_repository.get_catalog_analytics()
    return catalog_analytics_payload(analytics)


async def _dashboard_sections(container: Any) -> dict[str, Any]:
    """Compose the dashboard payload from existing repositories (additive)."""
    seeds = container.seed_repository
    tracks = container.track_repository
    analytics = await tracks.get_catalog_analytics()
    heard = await tracks.get_heard_ids()
    recent = await tracks.list_embedded(12, features_first=True)
    set_counts = (
        await container.set_repository.count()
        if getattr(container, "set_repository", None)
        else 0
    )
    return {
        "stats": {
            "seeds": {
                "total": await seeds.count(),
                "pending": await seeds.count_by_status("pending"),
                "fetched": await seeds.count_by_status("fetched"),
                "failed": await seeds.count_by_status("failed"),
                "electronic": await seeds.count_by_category("electronic"),
                "general": await seeds.count_by_category("general"),
            },
            "tracks": {
                "total": await tracks.count(),
                "embedded": await tracks.count_embedded(),
                "heard": len(heard),
            },
            "sets": {"total": set_counts},
        },
        "analytics": catalog_analytics_payload(analytics),
        "recent_tracks": [track_payload(t, heard=heard) for t in recent],
    }


@router.get("/catalog/dashboard")
async def get_catalog_dashboard(
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """One-shot dashboard bundle: stats, analytics, and recent tracks."""
    return await _dashboard_sections(container)


@router.get("/catalog/artists")
async def get_artists_summary(
    q: str | None = Query(None),
    genre: str | None = Query(None),
    source: str | None = Query(None),
    min_year: int | None = Query(None, ge=1900, le=2100),
    sort: str = Query("tracks_desc"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    taste_mode: str = Query("both"),
    liked_only: bool = Query(False),
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Search and browse aggregated artist summaries."""
    liked_keys = (
        await container.liked_artist_repository.get_liked_keys()
        if getattr(container, "liked_artist_repository", None)
        else frozenset()
    )
    mode = taste_mode if taste_mode in ("local", "liked", "both") else "both"
    summaries, total = await container.track_repository.list_artists_summary(
        query=q,
        genre=genre,
        source=source,
        min_year=min_year,
        sort=sort,
        limit=limit,
        offset=offset,
        taste_mode=mode,
        liked_artist_keys=liked_keys,
        liked_only=liked_only,
    )
    return {
        "artists": [artist_summary_payload(s) for s in summaries],
        "total": total,
    }


@router.get("/catalog/taste-ranking")
async def get_taste_ranking(
    mode: str = Query("both"),
    genre: str | None = Query(None),
    source: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    liked_weight: float = Query(2.0, ge=0.0, le=10.0),
    local_weight: float = Query(1.0, ge=0.0, le=10.0),
    max_per_artist: int = Query(0, ge=0, le=50),
    hide_heard: bool = Query(False),
    exclude_local: bool = Query(False),
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Rank the full embedded catalog against the CLAP taste vector.

    ``mode`` selects the taste profile seeds: ``local`` (downloaded tracks),
    ``liked`` (liked artists' catalog tracks) or ``both`` (liked weighted 2x by
    default; ``liked_weight``/``local_weight`` tune that blend for
    ``mode="both"``). ``max_per_artist`` caps tracks per artist (0 = unlimited);
    ``hide_heard`` and ``exclude_local`` narrow the ranked candidates.
    """
    liked_keys = (
        await container.liked_artist_repository.get_liked_keys()
        if getattr(container, "liked_artist_repository", None)
        else frozenset()
    )
    taste_mode = mode if mode in ("local", "liked", "both") else "both"
    ranking = await container.track_repository.get_track_taste_ranking(
        mode=taste_mode,
        liked_artist_keys=liked_keys,
        genre=genre,
        source=source,
        liked_weight=liked_weight,
        local_weight=local_weight,
        max_per_artist=max_per_artist,
        hide_heard=hide_heard,
        exclude_local=exclude_local,
    )
    ordered = sorted(ranking.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    tracks = await container.track_repository.get_many([tid for tid, _ in ordered])
    scores = dict(ordered)
    heard = await container.track_repository.get_heard_ids()
    matches = [
        {**track_payload(t, heard=heard), "taste_percent": scores[t.id]}
        for t in tracks
        if t.id in scores
    ]
    matches.sort(key=lambda m: m["taste_percent"], reverse=True)
    return {"matches": matches, "total": len(matches), "mode": taste_mode}


@router.get("/catalog/artists/{artist_name}/tracks")
async def get_artist_tracks(
    artist_name: str,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """List catalog tracks for a specific artist."""
    tracks = await container.track_repository.list_by_artist(
        artist_name, limit=limit, offset=offset
    )
    heard = await container.track_repository.get_heard_ids()
    return {
        "artist": artist_name,
        "tracks": [track_payload(t, heard=heard) for t in tracks],
    }


@router.delete("/catalog/tracks/{track_id}")
async def delete_track(
    track_id: str,
    blacklist: bool = Query(False),
    reason: str | None = Query(None),
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Delete a track from the catalog, optionally blacklisting it.

    Never deletes user audio files on disk (only DB rows).
    """
    result = await container.manage_catalog.delete_track(
        track_id, blacklist=blacklist, reason=reason
    )
    return {
        "success": result.deleted,
        "track_id": track_id,
        "blacklisted": result.blacklisted,
    }


@router.post("/catalog/artists/bulk-delete")
async def bulk_delete_artists_endpoint(
    req: BulkDeleteArtistsRequest,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Bulk delete multiple artists, optionally blacklisting them.

    Never deletes user audio files on disk (only DB rows).
    """
    res = await container.manage_catalog.bulk_delete_artists(
        req.artist_names,
        blacklist=req.blacklist,
        reason=req.reason,
    )
    return bulk_delete_artists_result_payload(res)


@router.post("/catalog/artists/bulk-cleanup/preview")
async def preview_bulk_cleanup_endpoint(
    req: BulkCleanupCriteriaRequest,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Preview catalog artists matching cleanup rules."""
    has_taste = req.max_taste_percent is not None
    has_genre = req.genre is not None and bool(req.genre.strip())
    if not has_taste and not has_genre:
        raise HTTPException(
            status_code=422,
            detail="At least one criteria (max_taste_percent or genre) must be provided",
        )
    try:
        criteria = BulkCleanupCriteria(
            max_taste_percent=req.max_taste_percent,
            taste_mode=req.taste_mode,
            genre=req.genre,
            source=req.source,
            protect_liked=req.protect_liked,
            protect_local=req.protect_local,
        )
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err

    preview = await container.manage_catalog.preview_bulk_cleanup(
        criteria, sample_limit=25
    )
    return {
        "artist_count": preview.artist_count,
        "track_count": preview.track_count,
        "skipped_count": preview.skipped_count,
        "sample_artists": [artist_summary_payload(a) for a in preview.sample_artists],
    }


@router.post("/catalog/artists/bulk-cleanup")
async def execute_bulk_cleanup_endpoint(
    req: BulkCleanupExecuteRequest,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Execute bulk deletion for catalog artists matching cleanup rules."""
    has_taste = req.max_taste_percent is not None
    has_genre = req.genre is not None and bool(req.genre.strip())
    if not has_taste and not has_genre:
        raise HTTPException(
            status_code=422,
            detail="At least one criteria (max_taste_percent or genre) must be provided",
        )
    try:
        criteria = BulkCleanupCriteria(
            max_taste_percent=req.max_taste_percent,
            taste_mode=req.taste_mode,
            genre=req.genre,
            source=req.source,
            protect_liked=req.protect_liked,
            protect_local=req.protect_local,
        )
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err

    res = await container.manage_catalog.execute_bulk_cleanup(
        criteria,
        blacklist=req.blacklist,
        reason=req.reason,
    )
    return bulk_delete_artists_result_payload(res)


@router.delete("/catalog/artists/{artist_name}")
async def delete_artist(
    artist_name: str,
    blacklist: bool = Query(False),
    reason: str | None = Query(None),
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Delete all tracks and seeds for an artist, optionally blacklisting them.

    Never deletes user audio files on disk (only DB rows).
    """
    result = await container.manage_catalog.delete_artist(
        artist_name, blacklist=blacklist, reason=reason
    )
    return {
        "success": True,
        "artist": artist_name,
        "tracks_deleted": result.tracks_deleted,
        "seed_removed": result.seed_removed,
        "blacklisted": result.blacklisted,
    }


@router.get("/catalog/blacklist")
async def get_blacklist(
    kind: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """List blocked artists and tracks."""
    entries = await container.manage_catalog.list_blacklist(
        kind=kind, query=q, limit=limit, offset=offset
    )
    total = await container.manage_catalog.count_blacklist(kind=kind)
    return {
        "entries": [blacklist_entry_payload(e) for e in entries],
        "total": total,
    }


@router.post("/catalog/blacklist")
async def add_blacklist(
    payload: BlacklistCreateRequest,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Add an artist or track to the blacklist."""
    if payload.kind == "track":
        if not payload.track_title:
            raise HTTPException(
                status_code=400, detail="track_title is required when kind='track'"
            )
        entry = await container.manage_catalog.add_blacklist_track(
            payload.name, payload.track_title, reason=payload.reason
        )
    else:
        entry = await container.manage_catalog.add_blacklist_artist(
            payload.name, reason=payload.reason
        )
    return blacklist_entry_payload(entry)


@router.delete("/catalog/blacklist/{entry_id}")
async def remove_blacklist(
    entry_id: int,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Remove an entry from the blacklist by ID."""
    removed = await container.manage_catalog.remove_blacklist_entry(entry_id)
    if not removed:
        raise HTTPException(
            status_code=404, detail=f"Blacklist entry {entry_id} not found"
        )
    return {"success": True, "id": entry_id}


@router.get("/catalog/seeds")
async def list_seeds(
    status: str | None = Query(None),
    source: str | None = Query(None),
    category: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """List pending/fetched/failed crawl seeds with breakdown stats."""
    seeds, total = await container.seed_repository.list_seeds(
        status=status,
        source=source,
        category=category,
        query=q,
        limit=limit,
        offset=offset,
    )
    breakdown = await container.seed_repository.get_breakdown()
    return {
        "seeds": [seed_payload(s) for s in seeds],
        "total": total,
        "breakdown": seed_breakdown_payload(breakdown),
    }


@router.delete("/catalog/seeds/{name:path}")
async def delete_seed(
    name: str,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Delete a seed by artist name."""
    deleted = await container.seed_repository.delete_by_name(name)
    return {"name": name, "deleted": deleted}


@router.post("/catalog/seeds/purge")
async def purge_seeds(
    payload: SeedPurgeRequest,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Purge seeds matching criteria (e.g. failed or pending from a source)."""
    purged = await container.seed_repository.purge_seeds(
        status=payload.status,
        source=payload.source,
        category=payload.category,
        exclude_sources=payload.exclude_sources,
    )
    return {"purged": purged}


@router.get("/catalog/liked-artists")
async def list_liked_artists(
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """List all user-liked artists."""
    if not getattr(container, "liked_artist_repository", None):
        return {"liked_artists": [], "total": 0}
    artists = await container.liked_artist_repository.list_all()
    return {
        "liked_artists": [liked_artist_payload(a) for a in artists],
        "total": len(artists),
    }


@router.post("/catalog/liked-artists/{artist_name:path}")
async def like_artist(
    artist_name: str,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Like an artist, bumping them in discovery and invalidating taste cache."""
    clean_name = artist_name.strip()
    if getattr(container, "blacklist_repository", None):
        norm_key = normalize_artist_key(clean_name)
        if await container.blacklist_repository.is_artist_blocked(norm_key):
            raise HTTPException(
                status_code=409,
                detail=f"Artist '{clean_name}' is blacklisted. Unblock first before liking.",
            )
    if not getattr(container, "liked_artist_repository", None):
        raise HTTPException(status_code=500, detail="LikedArtistRepository unavailable")
    liked = await container.liked_artist_repository.like(clean_name)
    if getattr(container, "seed_repository", None) and hasattr(
        container.seed_repository, "record_discovery"
    ):
        await container.seed_repository.record_discovery(
            [SeedArtist(clean_name, 1.0, "electronic", source="liked-artist")],
            priority_increment=0.5,
        )
    if hasattr(container.track_repository, "_invalidate_taste_cache"):
        container.track_repository._invalidate_taste_cache()
    return {"liked": True, "artist": liked_artist_payload(liked)}


@router.delete("/catalog/liked-artists/{artist_name:path}")
async def unlike_artist(
    artist_name: str,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Unlike an artist."""
    clean_name = artist_name.strip()
    if not getattr(container, "liked_artist_repository", None):
        return {"deleted": False, "unliked": False, "artist": clean_name}
    deleted = await container.liked_artist_repository.unlike(clean_name)
    if hasattr(container.track_repository, "_invalidate_taste_cache"):
        container.track_repository._invalidate_taste_cache()
    return {"deleted": deleted, "unliked": deleted, "artist": clean_name}


@router.get("/catalog/liked-artists/similar")
async def get_similar_liked_artists(
    artist: str | None = Query(None),
    min_year: int | None = Query(None, ge=1900, le=2100),
    limit: int = Query(24, ge=1, le=100),
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Discover other artists in the catalog similar to liked artists or a specific artist."""
    liked_repo = getattr(container, "liked_artist_repository", None)
    sqlite = getattr(container, "sqlite", None)
    vectors = getattr(container, "vectors", None)
    seed_artists = await _resolve_seed_artists(artist, liked_repo)

    if not seed_artists or not sqlite or not vectors:
        return {"seed_artists": seed_artists, "seed_tracks_used": 0, "items": []}

    normalized_seed_keys = {normalize_artist_key(a) for a in seed_artists}
    liked_keys = await liked_repo.get_liked_keys() if liked_repo else frozenset()

    all_embedded = await sqlite.fetchall(
        "SELECT id, artist FROM tracks WHERE is_embedded = 1"
    )
    seed_track_ids = _seed_track_ids(all_embedded, normalized_seed_keys)
    if not seed_track_ids:
        return {"seed_artists": seed_artists, "seed_tracks_used": 0, "items": []}

    track_sims = await vectors.compute_similarity_to_seed_ids(seed_track_ids)
    if not track_sims:
        return {
            "seed_artists": seed_artists,
            "seed_tracks_used": len(seed_track_ids),
            "items": [],
        }

    artist_rows = await _embedded_artist_rows(sqlite)
    matches = _score_similar_artists(
        artist_rows,
        all_embedded,
        track_sims,
        normalized_seed_keys,
        liked_keys,
        min_year,
    )
    matches.sort(key=lambda m: (m.similarity_percent, m.track_count), reverse=True)
    sliced = matches[:limit]
    return {
        "seed_artists": seed_artists,
        "seed_tracks_used": len(seed_track_ids),
        "items": [similar_artist_payload(m) for m in sliced],
    }


async def _resolve_seed_artists(artist: str | None, liked_repo: Any) -> list[str]:
    """Explicit ``artist`` query param wins; otherwise all liked artists."""
    if artist and artist.strip():
        return [artist.strip()]
    if liked_repo:
        all_liked = await liked_repo.list_all()
        return [a.artist_name for a in all_liked]
    return []


def _seed_track_ids(
    all_embedded: list[Any], normalized_seed_keys: set[str]
) -> list[str]:
    return [
        str(r["id"])
        for r in all_embedded
        if normalize_artist_key(str(r["artist"])) in normalized_seed_keys
    ]


async def _embedded_artist_rows(sqlite: Any) -> list[Any]:
    return await sqlite.fetchall(
        """
        SELECT
            artist,
            COUNT(*) AS track_count,
            SUM(is_embedded) AS embedded_count,
            MIN(bpm) AS bpm_min,
            MAX(bpm) AS bpm_max,
            MIN(release_year) AS year_min,
            MAX(release_year) AS year_max,
            GROUP_CONCAT(DISTINCT genre) AS genres_concat
        FROM tracks
        WHERE is_embedded = 1
        GROUP BY artist
        """
    )


def _score_similar_artists(
    artist_rows: list[Any],
    all_embedded: list[Any],
    track_sims: dict[str, float],
    normalized_seed_keys: set[str],
    liked_keys: frozenset[str] | set[str],
    min_year: int | None,
) -> list[SimilarArtistMatch]:
    """Average the per-track similarities of every non-seed artist."""
    artist_scores: dict[str, list[float]] = {}
    for r in all_embedded:
        art = str(r["artist"])
        if normalize_artist_key(art) in normalized_seed_keys:
            continue
        tid = str(r["id"])
        if tid in track_sims:
            artist_scores.setdefault(art, []).append(track_sims[tid])

    matches = []
    for row in artist_rows:
        art = str(row["artist"])
        norm_k = normalize_artist_key(art)
        scores = artist_scores.get(art, [])
        if norm_k in normalized_seed_keys or not scores:
            continue
        avg_sim = round(sum(scores) / len(scores), 1)
        y_min = int(row["year_min"]) if row["year_min"] is not None else None
        y_max = int(row["year_max"]) if row["year_max"] is not None else None
        if min_year is not None and (y_max is None or y_max < min_year):
            continue
        genres_raw = row["genres_concat"] or ""
        genres = tuple(g for g in genres_raw.split(",") if g)
        b_min = float(row["bpm_min"]) if row["bpm_min"] is not None else None
        b_max = float(row["bpm_max"]) if row["bpm_max"] is not None else None

        matches.append(
            SimilarArtistMatch(
                artist=art,
                similarity_percent=avg_sim,
                track_count=int(row["track_count"] or 0),
                embedded_count=int(row["embedded_count"] or 0),
                genres=genres,
                bpm_min=b_min,
                bpm_max=b_max,
                year_min=y_min,
                year_max=y_max,
                is_liked=norm_k in liked_keys,
            )
        )
    return matches


__all__ = ["router"]
