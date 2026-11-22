"""Shared route helpers."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request


def get_container(request: Request) -> Any:
    """Return the lifespan-owned container or fail with 503."""
    container = request.app.state.container
    if container is None:
        raise HTTPException(status_code=503, detail="the service is still starting")
    return container


def get_job_manager(request: Request) -> Any:
    """Return the lifespan-owned job manager."""
    manager = request.app.state.job_manager
    if manager is None:
        raise HTTPException(status_code=503, detail="the service is still starting")
    return manager


__all__ = ["get_container", "get_job_manager"]
