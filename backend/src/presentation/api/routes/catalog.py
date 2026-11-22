"""Catalog endpoints: stats, search, dig, vibe search, and heard state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from domain.entities.search import SearchFilter
from domain.use_cases import TrackNotEmbeddedError, TrackNotFoundError

from ..schemas import (
    HeardRequest,
    ResetEmbeddingsRequest,
    VibeSearchRequest,
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
            status_code=400, detail="send {\"confirm\": true} to drop embeddings"
        )
    cleared = await container.track_repository.reset_embeddings()
    return {"cleared": cleared}


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
        raise HTTPException(
            status_code=404, detail="Audio file does not exist on disk"
        )
    return FileResponse(
        path=file_path,
        filename=file_path.name,
    )


__all__ = ["router"]
