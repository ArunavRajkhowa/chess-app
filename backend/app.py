"""FastAPI app factory: API routers first, the built frontend mounted last. Starts the engine
pool and the SQLite store on startup; without an engine the app refuses to start and says why."""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .engine.pool import pool
from .logging_setup import configure_logging
from .openings.book import load_book
from .settings import REPO_ROOT, settings
from .storage.db import database

_FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
_access_log = logging.getLogger("chess.request")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.start()
    load_book()
    await pool.start()
    try:
        yield
    finally:
        await pool.stop()
        await database.stop()


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Chess Coach", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = uuid.uuid4().hex[:12]
        started = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        if request.url.path.startswith("/api/"):
            _access_log.info(
                "%s %s -> %s (%.0fms) rid=%s",
                request.method, request.url.path, response.status_code,
                (time.monotonic() - started) * 1000, rid,
            )
        return response

    from .routers import register_routers

    register_routers(app)

    if _FRONTEND_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")
        for sub in ("pieces", "sounds", "engine"):
            d = _FRONTEND_DIST / sub
            if d.is_dir():
                app.mount(f"/{sub}", StaticFiles(directory=d), name=sub)

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            """Every non-API path serves index.html so client-side routes survive a refresh."""
            candidate = _FRONTEND_DIST / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(_FRONTEND_DIST / "index.html")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app:app", host=settings.HOST, port=settings.PORT, reload=True)
