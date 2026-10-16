"""GET /api/health: proves the engine and the store are up and names the engine in use."""
from __future__ import annotations

from fastapi import APIRouter

from ..engine.pool import pool
from ..openings.book import load_book
from ..settings import settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {
        "ok": pool.ready,
        "engine": {"name": pool.id_name, "kind": pool.kind, "command": pool.command},
        "openings": len(load_book().all),
        "coach": {"llm": bool(settings.ANTHROPIC_API_KEY), "model": settings.ANTHROPIC_MODEL},
    }
