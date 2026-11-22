"""FastAPI application factory for the local Mission Control UI.

The app owns exactly one :class:`~container.Container` for its whole lifetime
(CLAP stays warm in VRAM; SQLite/LanceDB have a single owner). Long jobs run as
``asyncio.Task`` objects over that container and stream progress over SSE.

Nothing here imports concrete data-layer classes: the container is created by
the composition root inside the lifespan.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from .job_manager import JobManager
from .routes import catalog, hardware, jobs, set_helper, sets

LOGGER = logging.getLogger(__name__)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
FRONTEND_DIR = REPOSITORY_ROOT / "frontend"


def create_app(container: Any | None = None) -> FastAPI:
    """Build the API app.

    ``container`` is a test seam: when omitted, the lifespan constructs and
    starts the real composition-root container. When supplied (tests, or an
    embedder that already owns one), the app uses it as-is and never closes it.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owns_container = app.state.container is None
        if owns_container:
            # Imported lazily so importing the API stays cheap for tests.
            from container import Container

            real_container = Container()
            await real_container.start()
            app.state.container = real_container
        LOGGER.info("DigDeeper Local API ready")
        try:
            yield
        finally:
            manager = app.state.job_manager
            if manager is not None and manager.active:
                await manager.cancel()
                await manager.wait()
            if owns_container:
                await app.state.container.close()

    app = FastAPI(
        title="DigDeeper Local",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.container = container
    app.state.job_manager = JobManager(lambda: app.state.container)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(jobs.router)
    app.include_router(catalog.router)
    app.include_router(sets.router)
    app.include_router(hardware.router)
    app.include_router(set_helper.router)

    @app.api_route(
        "/api/{full_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    async def api_catch_all(full_path: str) -> None:
        raise HTTPException(status_code=404, detail="API endpoint not found")

    if FRONTEND_DIR.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=FRONTEND_DIR, html=True),
            name="frontend",
        )
    return app


__all__ = ["FRONTEND_DIR", "REPOSITORY_ROOT", "create_app"]
