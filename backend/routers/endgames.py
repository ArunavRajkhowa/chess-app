"""Endgame trainer API: the themed positions, a timed challenge set, and attempt records.
Moves are played through /api/learn/drill/move, the same engine reply used by lesson drills; an
attempt sends the whole line and the server replays it to decide success."""
from __future__ import annotations

import random

import chess
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..content.endgames import load_endgames
from ..storage.db import database
from .learn import drill_outcome, material_balance

router = APIRouter(prefix="/api/endgames", tags=["endgames"])
CHALLENGE_SIZE = 5


class EndgameAttempt(BaseModel):
    key: str
    line: list[str] = Field(default_factory=list, max_length=200)  # every move of the attempt, both sides, UCI
    seconds: float = Field(ge=0)
    mode: str = "practice"


def judge_line(position: dict, line: list[str]) -> tuple[bool, int]:
    """Replays an attempt with python-chess under the drill rules: (success, the learner's move count).
    Reaching the move limit holds a draw or survive goal and fails every other goal."""
    board = chess.Board(position["fen"])
    learner = board.turn
    start = material_balance(board, learner)
    learner_moves = 0
    for uci in line:
        try:
            mv = chess.Move.from_uci(uci)
        except ValueError:
            raise HTTPException(400, f"bad move {uci!r} in the attempt line")
        if mv not in board.legal_moves:
            raise HTTPException(400, f"illegal move {uci} in {board.fen()}")
        by_learner = board.turn == learner
        board.push(mv)
        learner_moves += by_learner
        outcome = drill_outcome(board, learner, position["goal"], mv if by_learner else None, start)
        if outcome:
            return outcome["result"] == "success", learner_moves
        if learner_moves >= position["max_moves"] and not by_learner:
            break
    held = learner_moves >= position["max_moves"] and position["goal"] in ("draw", "survive")
    return held, learner_moves


@router.get("")
async def index() -> dict:
    data = load_endgames()
    stats = await database.get_player_value("endgame_stats", {})
    positions = [{**p, "best": stats.get(p["key"])} for p in data["positions"]]
    return {"themes": data["themes"], "positions": positions}


@router.get("/challenge")
async def challenge(theme: str = Query(...)) -> dict:
    data = load_endgames()
    pool = [p for p in data["positions"] if p["theme"] == theme]
    if not pool:
        raise HTTPException(404, f"no theme {theme!r}")
    rng = random.Random()
    pick = rng.sample(pool, min(CHALLENGE_SIZE, len(pool)))
    pick.sort(key=lambda p: p["level"])
    return {"theme": theme, "positions": pick}


@router.post("/attempt")
async def attempt(req: EndgameAttempt) -> dict:
    position = next((p for p in load_endgames()["positions"] if p["key"] == req.key), None)
    if position is None:
        raise HTTPException(404, "no such position")
    success, moves = judge_line(position, req.line)
    stats = await database.get_player_value("endgame_stats", {})
    prev = stats.get(req.key) or {"solved": 0, "tried": 0, "best_moves": None, "best_seconds": None}
    prev["tried"] += 1
    if success:
        prev["solved"] += 1
        prev["best_moves"] = moves if prev["best_moves"] is None else min(prev["best_moves"], moves)
        prev["best_seconds"] = req.seconds if prev["best_seconds"] is None else min(prev["best_seconds"], req.seconds)
    stats[req.key] = prev
    await database.set_player_value("endgame_stats", stats)
    history = await database.get_player_value("endgame_history", [])
    history = (history + [{"key": req.key, "success": success, "moves": moves, "seconds": req.seconds, "mode": req.mode}])[-200:]
    await database.set_player_value("endgame_history", history)
    return {"success": success, "moves": moves, "stats": prev}
