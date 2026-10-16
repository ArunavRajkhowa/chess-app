"""Master games API: the curated library by theme and level, one game with its comments, and the
guess-the-move scorer that compares the learner's guess with the master's move using the engine."""
from __future__ import annotations

import chess
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..content.games import THEME_NAMES, find_game, load_games
from ..engine.pool import pool
from ..engine.score import cp_from_score, win_percent_from_cp

router = APIRouter(prefix="/api/games", tags=["games"])
GUESS_DEPTH = 12


class GuessRequest(BaseModel):
    game_id: str
    ply: int  # the ply the learner is guessing (1-based)
    move: str  # uci


@router.get("")
async def index(theme: str | None = None, level: int | None = None) -> dict:
    games = load_games()
    if theme:
        games = [g for g in games if theme in g.themes]
    if level is not None:
        games = [g for g in games if g.level <= level]
    counts: dict[str, int] = {}
    for g in load_games():
        for t in g.themes:
            counts[t] = counts.get(t, 0) + 1
    themes = [{"key": k, "name": THEME_NAMES.get(k, k.replace("-", " ").title()), "count": n} for k, n in sorted(counts.items(), key=lambda kv: -kv[1])]
    return {"games": [g.summary() for g in games], "themes": themes, "total": len(load_games())}


@router.get("/{game_id}")
async def detail(game_id: str) -> dict:
    g = find_game(game_id)
    if not g:
        raise HTTPException(404, "no such game")
    return g.detail()


@router.post("/guess")
async def guess(req: GuessRequest) -> dict:
    """Scores a guess: 'master' if it matches, else the engine's view of both moves."""
    g = find_game(req.game_id)
    if not g or not (1 <= req.ply <= len(g.plies)):
        raise HTTPException(404, "no such game or ply")
    board = chess.Board() if req.ply == 1 else chess.Board(g.plies[req.ply - 2]["fen"])
    master = chess.Move.from_uci(g.plies[req.ply - 1]["uci"])
    try:
        mv = chess.Move.from_uci(req.move)
    except ValueError:
        raise HTTPException(400, "bad move")
    if mv not in board.legal_moves:
        raise HTTPException(400, "illegal move")
    if mv == master:
        return {"verdict": "master", "points": 3, "master_san": board.san(master), "your_san": board.san(mv), "note": "That is the move played in the game."}
    mover = board.turn
    b1 = board.copy(); b1.push(mv)
    b2 = board.copy(); b2.push(master)
    i1 = await pool.analyse(b1, depth=GUESS_DEPTH)
    i2 = await pool.analyse(b2, depth=GUESS_DEPTH)
    w1 = win_percent_from_cp(cp_from_score(i1[0]["score"], mover)) if i1 else (100.0 if b1.is_checkmate() else 50.0)
    w2 = win_percent_from_cp(cp_from_score(i2[0]["score"], mover)) if i2 else (100.0 if b2.is_checkmate() else 50.0)
    diff = w2 - w1
    if diff <= 2:
        verdict, points, note = "excellent", 2, "As good as the master's move by the engine."
    elif diff <= 8:
        verdict, points, note = "good", 1, "A reasonable move; the game move was a little stronger."
    else:
        verdict, points, note = "weak", 0, "The game move was clearly better."
    return {"verdict": verdict, "points": points, "master_san": board.san(master), "your_san": board.san(mv), "win_yours": round(w1, 1), "win_master": round(w2, 1), "note": note}
