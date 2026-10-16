"""Puzzle API: the next rated puzzle, custom puzzles by theme, attempts with Glicko-2 updates,
Puzzle Rush runs, the daily puzzle, and the solver's stats."""
from __future__ import annotations

import datetime as dt
import random

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..puzzles.glicko import Rating, update
from ..puzzles.store import load_library
from ..storage.db import database

router = APIRouter(prefix="/api/puzzles", tags=["puzzles"])

RATING_KEY = "puzzle_rating"
RUSH_LENGTH = 60


class AttemptRequest(BaseModel):
    solved: bool
    seconds: float | None = None
    mode: str = Field("rated", pattern="^(rated|custom|rush|daily)$")


async def _player_rating() -> Rating:
    d = await database.get_player_value(RATING_KEY, None)
    return Rating(**d) if d else Rating()


async def _recent_ids(limit: int = 300) -> set[str]:
    rows = await database.fetch_all("SELECT puzzle_id FROM puzzle_attempts ORDER BY id DESC LIMIT ?", (limit,))
    return {r["puzzle_id"] for r in rows}


@router.get("/themes")
async def themes() -> dict:
    lib = load_library()
    return {"themes": lib.themes(), "total": len(lib.all)}


@router.get("/next")
async def next_puzzle(
    themes: str | None = Query(None, description="comma separated theme keys"),
    min_rating: int | None = None,
    max_rating: int | None = None,
) -> dict:
    lib = load_library()
    if not lib.all:
        raise HTTPException(503, "no puzzles installed; run scripts/generate_puzzles.py")
    player = await _player_rating()
    theme_list = [t for t in (themes or "").split(",") if t]
    p = lib.pick(rating=player.rating, themes=theme_list or None, exclude=await _recent_ids(),
                 min_rating=min_rating, max_rating=max_rating)
    if p is None:
        raise HTTPException(404, "no puzzle matches those filters")
    return {"puzzle": p.public(), "player_rating": round(player.rating)}


@router.get("/daily")
async def daily() -> dict:
    lib = load_library()
    if not lib.all:
        raise HTTPException(503, "no puzzles installed")
    today = dt.date.today().isoformat()
    rng = random.Random(today)
    candidates = [p for p in lib.all if 1200 <= p.rating <= 2000] or lib.all
    p = rng.choice(candidates)
    return {"date": today, "puzzle": p.public()}


@router.get("/{puzzle_id}")
async def get_puzzle(puzzle_id: str) -> dict:
    p = load_library().by_id.get(puzzle_id)
    if not p:
        raise HTTPException(404, "no such puzzle")
    return {"puzzle": p.public()}


@router.post("/{puzzle_id}/attempt")
async def attempt(puzzle_id: str, req: AttemptRequest) -> dict:
    p = load_library().by_id.get(puzzle_id)
    if not p:
        raise HTTPException(404, "no such puzzle")
    before = await _player_rating()
    after = before
    if req.mode == "rated":
        after = update(before, Rating(rating=p.rating, rd=p.rd), 1.0 if req.solved else 0.0)
        await database.set_player_value(RATING_KEY, {"rating": after.rating, "rd": after.rd, "volatility": after.volatility})
    await database.execute(
        "INSERT INTO puzzle_attempts(puzzle_id, solved, seconds, rating_before, rating_after, mode) VALUES(?,?,?,?,?,?)",
        (puzzle_id, int(req.solved), req.seconds, before.rating, after.rating, req.mode),
    )
    return {"solved": req.solved, "rating_before": round(before.rating), "rating_after": round(after.rating),
            "delta": round(after.rating - before.rating), "puzzle_rating": p.rating}


@router.get("/rush/start")
async def rush_start(mode: str = Query("3m", pattern="^(3m|5m|survival)$")) -> dict:
    """A ramp of puzzles from very easy to hard. Difficulty rises with the index."""
    lib = load_library()
    if not lib.all:
        raise HTTPException(503, "no puzzles installed")
    rng = random.Random()
    seq = []
    used: set[str] = set()
    for i in range(RUSH_LENGTH):
        target = 500 + i * 35
        p = lib.pick(rating=target, themes=None, exclude=used, spread=120, rng=rng)
        if p is None or p.id in used:
            break
        used.add(p.id)
        seq.append(p.public())
    return {"mode": mode, "seconds": {"3m": 180, "5m": 300, "survival": None}[mode], "strikes": 3, "puzzles": seq}


class RushResult(BaseModel):
    mode: str
    score: int
    wrong: int
    seconds: float


@router.post("/rush/finish")
async def rush_finish(req: RushResult) -> dict:
    best = await database.get_player_value(f"rush_best_{req.mode}", 0)
    is_best = req.score > best
    if is_best:
        await database.set_player_value(f"rush_best_{req.mode}", req.score)
    history = await database.get_player_value(f"rush_history_{req.mode}", [])
    history = (history + [{"score": req.score, "wrong": req.wrong, "seconds": req.seconds, "at": dt.datetime.now().isoformat(timespec="seconds")}])[-50:]
    await database.set_player_value(f"rush_history_{req.mode}", history)
    return {"best": max(best, req.score), "new_best": is_best, "history": history}


@router.get("/stats/me")
async def stats() -> dict:
    player = await _player_rating()
    rows = await database.fetch_all("SELECT solved, mode, created_at, rating_after, puzzle_id FROM puzzle_attempts ORDER BY id DESC LIMIT 500")
    rated = [r for r in rows if r["mode"] == "rated"]
    solved = sum(1 for r in rated if r["solved"])
    lib = load_library()
    by_theme: dict[str, dict[str, int]] = {}
    for r in rated:
        p = lib.by_id.get(r["puzzle_id"])
        if not p:
            continue
        for t in p.themes:
            d = by_theme.setdefault(t, {"tried": 0, "solved": 0})
            d["tried"] += 1
            d["solved"] += int(r["solved"])
    weakest = sorted((t for t in by_theme.items() if t[1]["tried"] >= 3), key=lambda kv: kv[1]["solved"] / kv[1]["tried"])[:5]
    return {
        "rating": round(player.rating), "rd": round(player.rd), "attempts": len(rated), "solved": solved,
        "accuracy": round(100 * solved / len(rated), 1) if rated else None,
        "history": [{"at": r["created_at"], "rating": round(r["rating_after"])} for r in reversed(rated[:100])],
        "by_theme": by_theme, "weakest_themes": [t for t, _ in weakest],
        "rush_best": {m: await database.get_player_value(f"rush_best_{m}", 0) for m in ("3m", "5m", "survival")},
    }
