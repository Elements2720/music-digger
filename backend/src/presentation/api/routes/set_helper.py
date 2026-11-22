"""Set Helper endpoints: transition scoring, next track suggestions, bridge finding, and set plans."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response

from domain.entities.set_plan import PlannedSet
from domain.use_cases.dig_similar_tracks import (
    TrackNotEmbeddedError,
    TrackNotFoundError,
)

from ..schemas import (
    AutoSequenceRequest,
    EvaluateSequenceRequest,
    FindBridgeRequest,
    PlannedSetCreateRequest,
    PlannedSetUpdateRequest,
    SuggestNextRequest,
    bridge_suggestion_payload,
    next_track_suggestion_payload,
    planned_set_payload,
    transition_evaluation_payload,
)
from . import get_container

router = APIRouter(prefix="/api/set-helper", tags=["set-helper"])


@router.post("/suggest-next")
async def suggest_next_track(
    payload: SuggestNextRequest,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Suggest top harmonic and BPM matching candidate tracks to follow a reference track."""
    helper = getattr(container, "dj_set_helper", None)
    if not helper:
        raise HTTPException(status_code=503, detail="DJSetHelper unavailable")

    try:
        suggestions = await helper.suggest_next(
            payload.from_track_id,
            limit=payload.limit,
            flow=payload.flow,
            local_only=payload.local_only,
            bpm_max_delta=payload.bpm_max_delta,
        )
    except TrackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TrackNotEmbeddedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    heard = (
        await container.track_repository.get_heard_ids()
        if hasattr(container.track_repository, "get_heard_ids")
        else frozenset()
    )
    return {
        "from_track_id": payload.from_track_id,
        "suggestions": [
            next_track_suggestion_payload(s, heard=heard) for s in suggestions
        ],
    }


@router.post("/bridge")
async def find_bridge_tracks(
    payload: FindBridgeRequest,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Find stepping-stone tracks bridging two musically distant tracks."""
    helper = getattr(container, "dj_set_helper", None)
    if not helper:
        raise HTTPException(status_code=503, detail="DJSetHelper unavailable")

    try:
        bridges = await helper.find_bridge(
            payload.track_a_id,
            payload.track_b_id,
            limit=payload.limit,
            local_only=payload.local_only,
        )
    except TrackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TrackNotEmbeddedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    heard = (
        await container.track_repository.get_heard_ids()
        if hasattr(container.track_repository, "get_heard_ids")
        else frozenset()
    )
    return {
        "track_a_id": payload.track_a_id,
        "track_b_id": payload.track_b_id,
        "bridges": [bridge_suggestion_payload(b, heard=heard) for b in bridges],
    }


@router.post("/auto-sequence")
async def auto_sequence_set(
    payload: AutoSequenceRequest,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Re-order tracks to maximize overall transition smoothness using nearest-neighbor + 2-opt search."""
    helper = getattr(container, "dj_set_helper", None)
    if not helper:
        raise HTTPException(status_code=503, detail="DJSetHelper unavailable")

    ordered_ids, avg_score = await helper.auto_sequence(
        payload.track_ids,
        flow=payload.flow,
        lock_first=payload.lock_first,
    )
    return {
        "ordered_track_ids": list(ordered_ids),
        "average_score": avg_score,
    }


@router.post("/evaluate")
async def evaluate_sequence(
    payload: EvaluateSequenceRequest,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Calculate step-by-step transition evaluations for every adjacent pair of tracks."""
    helper = getattr(container, "dj_set_helper", None)
    if not helper:
        raise HTTPException(status_code=503, detail="DJSetHelper unavailable")

    evals = await helper.evaluate_sequence(payload.track_ids, flow=payload.flow)
    return {
        "transitions": [transition_evaluation_payload(ev) for ev in evals],
    }


@router.get("/sets")
async def list_planned_sets(
    container: Any = Depends(get_container),
) -> list[dict[str, Any]]:
    """List all user-saved planned sets."""
    repo = getattr(container, "planned_set_repository", None)
    if not repo:
        return []
    sets = await repo.list_all()
    return [planned_set_payload(s) for s in sets]


@router.post("/sets")
async def create_planned_set(
    payload: PlannedSetCreateRequest,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Save a new planned set."""
    repo = getattr(container, "planned_set_repository", None)
    if not repo:
        raise HTTPException(status_code=503, detail="PlannedSetRepository unavailable")

    pset = PlannedSet(
        id=None,
        name=payload.name.strip() or "Untitled Set",
        track_ids=tuple(payload.track_ids),
    )
    saved = await repo.save(pset)
    return planned_set_payload(saved)


@router.get("/sets/{set_id}")
async def get_planned_set(
    set_id: int,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Fetch a planned set by ID along with full track metadata."""
    repo = getattr(container, "planned_set_repository", None)
    if not repo:
        raise HTTPException(status_code=503, detail="PlannedSetRepository unavailable")

    pset = await repo.get_by_id(set_id)
    if pset is None:
        raise HTTPException(status_code=404, detail=f"Planned set {set_id} not found")

    tracks = []
    if hasattr(container.track_repository, "get_by_id"):
        for tid in pset.track_ids:
            t = await container.track_repository.get_by_id(tid)
            if t is not None:
                tracks.append(t)

    heard = (
        await container.track_repository.get_heard_ids()
        if hasattr(container.track_repository, "get_heard_ids")
        else frozenset()
    )
    return planned_set_payload(pset, tracks=tracks, heard=heard)


@router.put("/sets/{set_id}")
async def update_planned_set(
    set_id: int,
    payload: PlannedSetUpdateRequest,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Update name or track sequence of a planned set."""
    repo = getattr(container, "planned_set_repository", None)
    if not repo:
        raise HTTPException(status_code=503, detail="PlannedSetRepository unavailable")

    existing = await repo.get_by_id(set_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Planned set {set_id} not found")

    new_name = payload.name.strip() if payload.name is not None else existing.name
    new_tracks = (
        tuple(payload.track_ids)
        if payload.track_ids is not None
        else existing.track_ids
    )

    updated = await repo.save(
        PlannedSet(
            id=set_id,
            name=new_name,
            track_ids=new_tracks,
            created_at=existing.created_at,
        )
    )
    return planned_set_payload(updated)


@router.delete("/sets/{set_id}")
async def delete_planned_set(
    set_id: int,
    container: Any = Depends(get_container),
) -> dict[str, Any]:
    """Delete a planned set."""
    repo = getattr(container, "planned_set_repository", None)
    if not repo:
        raise HTTPException(status_code=503, detail="PlannedSetRepository unavailable")

    deleted = await repo.delete(set_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Planned set {set_id} not found")
    return {"deleted": True, "id": set_id}


@router.get("/sets/{set_id}/export.m3u8")
async def export_planned_set_m3u8(
    set_id: int,
    container: Any = Depends(get_container),
) -> Response:
    """Export the planned set as a UTF-8 M3U8 playlist with local files or stream URLs."""
    repo = getattr(container, "planned_set_repository", None)
    helper = getattr(container, "dj_set_helper", None)
    if not repo or not helper:
        raise HTTPException(status_code=503, detail="Set helper services unavailable")

    pset = await repo.get_by_id(set_id)
    if pset is None:
        raise HTTPException(status_code=404, detail=f"Planned set {set_id} not found")

    content = await helper.export_m3u8(pset.name, pset.track_ids)
    safe_name = re.sub(r'[\/:*?"<>|]+', "_", pset.name.strip() or f"set_{set_id}")

    return Response(
        content=content.encode("utf-8"),
        media_type="application/x-mpegurl",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}.m3u8"',
        },
    )


__all__ = ["router"]
