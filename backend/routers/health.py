"""GET /api/health: proves the engine and the store are up and names the engine in use."""
from __future__ import annotations

from fastapi import APIRouter

from ..coach.client import llm_enabled, llm_model, llm_problem, llm_provider
from ..engine.pool import pool
from ..openings.book import load_book

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {
        "ok": pool.ready,
        "engine": {"name": pool.id_name, "kind": pool.kind, "command": pool.command},
        "openings": len(load_book().all) if load_book.cache_info().currsize else None,  # None until the book is warm
        "coach": {"llm": llm_enabled(), "provider": llm_provider(), "model": llm_model(), "problem": llm_problem()},
    }

