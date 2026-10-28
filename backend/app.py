"""FastAPI app factory: API routers first, the built frontend mounted last. Starts the engine
pool and the SQLite store on startup; without an engine the app refuses to start and says why."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

import chess
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .engine.pool import IllegalPosition, pool
from .logging_setup import configure_logging
from .bots import maia
from .bots.specialists import specialist_bots
from .content.lessons import load_curriculum
from .openings.book import load_book
from .plans import catalog
from .routers.account import current_player
from .settings import REPO_ROOT, settings
from .storage.db import database

_FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
_access_log = logging.getLogger("chess.request")


def _warm_content() -> None:
    """Builds the cached content once at start, so no request pays for it."""
    started = time.monotonic()
    load_book()
    maia.policy(chess.Board(), 1500, 1500)  # loads the bots' Maia-3 model (10-20 s on a small host)
    specialist_bots()  # the courses, the master games and the endgames
    load_curriculum()
    for family in catalog.families():
        catalog.groups_of(family)
    catalog.opening_puzzles("")  # the puzzle library and its opening tags
    logging.getLogger("chess.app").info("content ready in %.1fs", time.monotonic() - started)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.start()
    await pool.start()
    # The port opens now; on a small host the content takes a minute, and a request that needs it
    # before then builds what it needs itself.
    warm = asyncio.create_task(asyncio.to_thread(_warm_content))
    try:
        yield
    finally:
        await warm
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

    @app.exception_handler(IllegalPosition)
    async def illegal_position(request: Request, exc: IllegalPosition) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    from .routers import register_routers

    register_routers(app)

    if _FRONTEND_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")
        for sub in ("pieces", "sounds", "engine"):
            d = _FRONTEND_DIST / sub
            if d.is_dir():
                app.mount(f"/{sub}", StaticFiles(directory=d), name=sub)

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str, request: Request):
            """Every non-API path serves index.html so client-side routes survive a refresh. A file is
            served only from inside frontend/dist; an unknown /api path is a 404, not the page."""
            if path.startswith("api/"):
                raise HTTPException(404, f"no API route /{path}")
            root = _FRONTEND_DIST.resolve()
            candidate = (root / path).resolve()
            if path and candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)
            page = FileResponse(root / "index.html")
            # The page brings the player cookie, so the app's parallel first calls share one guest.
            await current_player(request, page)
            return page

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app:app", host=settings.HOST, port=settings.PORT, reload=True,
                forwarded_allow_ips=settings.FORWARDED_ALLOW_IPS or None)
