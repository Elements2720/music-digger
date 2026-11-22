"""DJ set endpoints: list stored sets and view tracklist / digs / neighbours."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from domain.entities.search import SearchFilter
from domain.use_cases import SetNotEmbeddedError

from ..schemas import (
    match_payload,
    passage_payload,
    set_match_payload,
    set_summary_payload,
)
from . import get_container

router = APIRouter(prefix="/api/sets", tags=["sets"])

_VIEWS = {"tracklist", "tracks", "sets"}


@router.get("")
async def list_sets(
    limit: int = Query(20, ge=1, le=200),
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Stored sets, newest first."""
    sets = await container.set_repository.list_all(limit)
    return {"sets": [set_summary_payload(dj_set) for dj_set in sets]}


@router.get("/{set_id}")
async def set_detail(
    set_id: str,
    view: str = Query("tracklist"),
    limit: int = Query(30, ge=1, le=500),
    bpm_tolerance: float | None = Query(None, ge=0),
    exclude_heard: bool = Query(False),
    genre: str | None = Query(None),
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """One set with the requested sub-view: tracklist, tracks, or sets."""
    if view not in _VIEWS:
        raise HTTPException(
            status_code=422,
            detail=f"view must be one of {sorted(_VIEWS)}, got {view!r}",
        )
    dj_set = await container.set_repository.get_by_id(set_id)
    if dj_set is None:
        raise HTTPException(status_code=404, detail=f"DJ set {set_id!r} not found")

    heard = await container.track_repository.get_heard_ids()
    payload: dict[str, Any] = {"set": set_summary_payload(dj_set), "view": view}

    if view == "tracklist":
        payload["passages"] = [
            passage_payload(passage, heard=heard)
            for passage in dj_set.ordered_passages()
        ]
        return payload

    try:
        if view == "tracks":
            search_filter = SearchFilter(
                limit=min(limit, 500),
                genre_filter=genre,
                exclude_heard=exclude_heard,
            )
            result = await container.find_similar_for_set.similar_tracks(
                set_id,
                search_filter,
                limit=limit,
                bpm_tolerance=bpm_tolerance,
            )
            payload["matches"] = [
                match_payload(match, heard=heard) for match in result.matches
            ]
        else:
            matches = await container.find_similar_for_set.similar_sets(
                set_id, limit=limit
            )
            payload["sets"] = [
                set_match_payload(match, heard=heard) for match in matches
            ]
    except SetNotEmbeddedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return payload


__all__ = ["router"]
