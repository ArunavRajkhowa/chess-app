"""GET /api/health: proves the engine and the store are up and names the engine in use."""
from __future__ import annotations

from fastapi import APIRouter

from ..content.endgames import load_endgames
from ..content.games import load_games
from ..content.lessons import load_curriculum
from ..engine.pool import pool
from ..openings.book import load_book
from ..puzzles.store import load_library
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


@router.post("/content/reload")
async def reload_content() -> dict:
    """Re-reads lessons, puzzles and master games from data/ without a restart."""
    load_curriculum.cache_clear()
    load_library.cache_clear()
    load_games.cache_clear()
    load_endgames.cache_clear()
    return {
        "lessons": sum(len(m.lessons) for m in load_curriculum()),
        "puzzles": len(load_library().all),
        "games": len(load_games()),
        "endgames": len(load_endgames()["positions"]),
    }
