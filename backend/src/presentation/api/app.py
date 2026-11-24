"""FastAPI application factory for the local Mission Control UI.

The app owns exactly one :class:`~container.Container` for its whole lifetime
(CLAP stays warm in VRAM; SQLite/LanceDB have a single owner). Long jobs run as
``asyncio.Task`` objects over that container and stream progress over SSE.

Nothing here imports concrete data-layer classes: the container is created by
the composition root inside the lifespan.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .job_manager import JobManager
from .routes import catalog, hardware, jobs, set_helper, sets

LOGGER = logging.getLogger(__name__)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
FRONTEND_DIR = REPOSITORY_ROOT / "frontend"


def _install_windows_loop_exception_handler(loop: asyncio.AbstractEventLoop) -> None:
    """Silence Windows proactor noise from ``206`` audio-range scrubbing.

    When the browser aborts an audio ``Range`` request mid-stream, the
    ``_ProactorBasePipeTransport`` surfaces ``ConnectionResetError``
    (winerror 10054) as a stray "Future exception was never retrieved" log.
    It is expected client behaviour, so drop it; everything else keeps the
    previous handling.
    """

    if sys.platform != "win32":
        return
    previous_handler = loop.get_exception_handler()

    def handler(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        exc = context.get("exception")
        if (
            isinstance(exc, ConnectionResetError)
            and getattr(exc, "winerror", None) == 10054
        ):
            return
        if previous_handler is not None:
            previous_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(handler)


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
        _install_windows_loop_exception_handler(asyncio.get_running_loop())
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

    dist_index = FRONTEND_DIR / "dist" / "index.html"
    if dist_index.is_file():
        # Built React bundle (ui-editorial-crate): assets + SPA fallback.
        app.mount(
            "/assets",
            StaticFiles(directory=FRONTEND_DIR / "dist" / "assets"),
            name="frontend-assets",
        )

        @app.get("/{spa_path:path}", include_in_schema=False)
        async def spa_fallback(spa_path: str) -> FileResponse:
            dist_dir = (FRONTEND_DIR / "dist").resolve()
            candidate = (dist_dir / spa_path).resolve()
            if spa_path and candidate.is_file() and candidate.is_relative_to(dist_dir):
                return FileResponse(candidate)
            return FileResponse(dist_index)

    elif FRONTEND_DIR.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=FRONTEND_DIR, html=True),
            name="frontend",
        )
    return app


__all__ = ["FRONTEND_DIR", "REPOSITORY_ROOT", "create_app"]
