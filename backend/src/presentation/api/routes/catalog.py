"""Catalog endpoints: stats, search, dig, vibe search, and heard state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from domain.entities.search import SearchFilter
from domain.use_cases import TrackNotEmbeddedError, TrackNotFoundError

from ..schemas import (
    BlacklistCreateRequest,
    HeardRequest,
    ResetEmbeddingsRequest,
    VibeSearchRequest,
    artist_summary_payload,
    blacklist_entry_payload,
    catalog_analytics_payload,
    match_payload,
    track_payload,
)
from . import get_container

router = APIRouter(prefix="/api", tags=["catalog"])


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


@router.get("/tracks/recent")
async def recent_tracks(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Recently embedded tracks for the Dig picker."""
    tracks = await container.track_repository.list_embedded(limit, offset=offset)
    heard = await container.track_repository.get_heard_ids()
    return {
        "tracks": [track_payload(track, heard=heard) for track in tracks],
        "embedded_total": await container.track_repository.count_embedded(),
    }


@router.get("/dig/{track_id}")
async def dig(
    track_id: str,
    limit: int = Query(10, ge=1, le=500),
    bpm_tolerance: float | None = Query(None, ge=0),
    harmonic: bool = Query(False),
    genre: str | None = Query(None),
    exclude_heard: bool = Query(False),
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Track-to-track similarity search (the CLI ``dig dig``)."""
    search_filter = SearchFilter(
        limit=limit,
        genre_filter=genre,
        exclude_heard=exclude_heard,
    )
    try:
        result = await container.dig_similar_tracks.execute(
            track_id,
            search_filter,
            bpm_tolerance=bpm_tolerance,
            harmonic=harmonic,
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


@router.get("/catalog/tracks/{track_id}/audio")
@router.get("/tracks/{track_id}/audio")
async def get_track_audio(
    track_id: str,
    container: Any = Depends(get_container),
) -> FileResponse:
    """Stream a local audio file safely."""
    track = await container.track_repository.get_by_id(track_id)
    if (
        track is None
        or not getattr(track, "local_path", None)
        or getattr(track, "source", None) != "local"
    ):
        raise HTTPException(
            status_code=404, detail=f"Local track {track_id!r} not found"
        )
    file_path = Path(track.local_path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Audio file does not exist on disk")
    return FileResponse(
        path=file_path,
        filename=file_path.name,
    )


@router.get("/catalog/analytics")
async def get_catalog_analytics(
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Catalog distributions and KPI statistics."""
    analytics = await container.track_repository.get_catalog_analytics()
    return catalog_analytics_payload(analytics)


@router.get("/catalog/artists")
async def get_artists_summary(
    q: str | None = Query(None),
    genre: str | None = Query(None),
    source: str | None = Query(None),
    sort: str = Query("tracks_desc"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Search and browse aggregated artist summaries."""
    summaries, total = await container.track_repository.list_artists_summary(
        query=q,
        genre=genre,
        source=source,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return {
        "artists": [artist_summary_payload(s) for s in summaries],
        "total": total,
    }


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


__all__ = ["router"]
