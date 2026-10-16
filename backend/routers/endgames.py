"""Endgame trainer API: the themed positions, a timed challenge set, and attempt records.
Moves are played through /api/learn/drill/move, the same engine reply used by lesson drills."""
from __future__ import annotations

import json
import random

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..content.endgames import load_endgames
from ..storage.db import database

router = APIRouter(prefix="/api/endgames", tags=["endgames"])
CHALLENGE_SIZE = 5


class EndgameAttempt(BaseModel):
    key: str
    success: bool
    moves: int
    seconds: float
    mode: str = "practice"


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
    keys = {p["key"] for p in load_endgames()["positions"]}
    if req.key not in keys:
        raise HTTPException(404, "no such position")
    stats = await database.get_player_value("endgame_stats", {})
    prev = stats.get(req.key) or {"solved": 0, "tried": 0, "best_moves": None, "best_seconds": None}
    prev["tried"] += 1
    if req.success:
        prev["solved"] += 1
        prev["best_moves"] = req.moves if prev["best_moves"] is None else min(prev["best_moves"], req.moves)
        prev["best_seconds"] = req.seconds if prev["best_seconds"] is None else min(prev["best_seconds"], req.seconds)
    stats[req.key] = prev
    await database.set_player_value("endgame_stats", stats)
    history = await database.get_player_value("endgame_history", [])
    history = (history + [{"key": req.key, "success": req.success, "moves": req.moves, "seconds": req.seconds, "mode": req.mode}])[-200:]
    await database.set_player_value("endgame_history", history)
    return {"stats": prev, "json": json.dumps(prev)}
