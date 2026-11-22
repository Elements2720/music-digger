"""Background job endpoints: start, inspect, cancel, and stream progress."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..job_manager import JobConflictError, JobParamError
from ..schemas import JobRequest
from . import get_job_manager

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("")
async def start_job(
    payload: JobRequest,
    manager: Any = Depends(get_job_manager),
) -> dict[str, Any]:
    """Launch one long-running use case; 409 while another job is active."""
    try:
        job = await manager.start(payload.kind, payload.params)
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except JobParamError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"job": job}


@router.get("/current")
async def current_job(manager: Any = Depends(get_job_manager)) -> dict[str, Any]:
    return {"job": manager.snapshot(), "active": manager.active}


@router.post("/cancel")
async def cancel_job(manager: Any = Depends(get_job_manager)) -> dict[str, Any]:
    """Cancel the active task; reports False when nothing is running."""
    return {"cancelled": await manager.cancel()}


@router.get("/stream")
async def stream_job(
    request: Request,
    manager: Any = Depends(get_job_manager),
) -> StreamingResponse:
    """Server-Sent Events: state snapshot, progress, terminal event."""
    return StreamingResponse(
        manager.stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = ["router"]
