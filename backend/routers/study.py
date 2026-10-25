"""Study API: why every move of a game was played and why not the alternatives (master games and
lesson model games, computed once and cached), and a grandmaster's assessment of any position."""
from __future__ import annotations

import chess
from fastapi import APIRouter, HTTPException

from ..content.games import find_game
from ..content.lessons import find_lesson
from ..engine.pool import pool
from ..storage import games as store
from ..study.annotate import study_or_start
from ..study.assess import assess
from .account import Player

router = APIRouter(prefix="/api/study", tags=["study"])


@router.get("/game/{game_id}")
async def game_study(game_id: str) -> dict:
    g = find_game(game_id)
    if not g:
        raise HTTPException(404, "no such game")
    return await study_or_start([chess.Move.from_uci(p["uci"]) for p in g.plies])


@router.get("/lesson/{lesson_id}/{index}")
async def lesson_study(lesson_id: str, index: int) -> dict:
    lsn = find_lesson(lesson_id)
    if not lsn or not (0 <= index < len(lsn.sections)) or lsn.sections[index]["type"] != "game":
        raise HTTPException(404, f"lesson {lesson_id} has no game section at index {index}")
    sec = lsn.sections[index]
    return await study_or_start([chess.Move.from_uci(p["uci"]) for p in sec["plies"]], sec["start_fen"])


@router.get("/mine/{game_id}")
async def my_game_study(game_id: str, player: Player) -> dict:
    """The player's own game studied the same way: why each move, why not the engine's choices."""
    row = await store.read_game(player, game_id)
    if not row or not row["moves"]:
        raise HTTPException(404, "no such game, or no moves yet")
    return await study_or_start([chess.Move.from_uci(m["uci"]) for m in row["moves"]], row.get("start_fen"), mine=True)


@router.get("/assess")
async def assess_position(fen: str) -> dict:
    try:
        board = chess.Board(fen)
    except ValueError:
        raise HTTPException(400, f"bad FEN {fen!r}")
    if not board.is_valid():
        raise HTTPException(400, f"illegal position {fen!r}")
    return await assess(board, pool)
