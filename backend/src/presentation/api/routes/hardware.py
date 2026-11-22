"""Hardware probe endpoint (the CLI ``dig check-hw``)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..schemas import hardware_payload
from . import get_container

router = APIRouter(prefix="/api", tags=["hardware"])


@router.get("/hardware")
async def hardware(container: Any = Depends(get_container)) -> dict[str, Any]:
    """Probe torch/CUDA/VRAM/RAM/ffmpeg off the event loop."""
    probe = container.hardware_probe
    if probe is None:
        raise HTTPException(status_code=503, detail="hardware probe unavailable")
    info = await asyncio.to_thread(probe.probe)
    return hardware_payload(info)


__all__ = ["router"]
