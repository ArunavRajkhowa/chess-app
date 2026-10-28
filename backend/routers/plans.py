"""Study plans API: a goal in the player's words becomes an ordered plan over the app's own
content, stored per player, with each step's progress read live from the existing records."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..plans.plan import TRACKED_KINDS, build_plan, closest_families, with_progress
from ..storage.db import database
from ..locks import KeyedLocks
from .account import Player
from .learn import player_level

LOGGER = logging.getLogger("chess.plans")
router = APIRouter(prefix="/api/plans", tags=["plans"])
_PLAN_LOCKS = KeyedLocks()  # one tick at a time per plan


class PlanRequest(BaseModel):
    goal: str = Field(min_length=2, max_length=500)


class StepTick(BaseModel):
    done: bool


async def _records(player: str) -> dict:
    """The player's records that step progress reads, as with_progress takes them."""
    lessons = await database.fetch_all("SELECT lesson_id FROM player_lessons WHERE player_id = ? AND completed_at IS NOT NULL", (player,))
    puzzles = await database.fetch_all("SELECT DISTINCT puzzle_id FROM puzzle_attempts WHERE player_id = ? AND solved = 1", (player,))
    games = await database.fetch_all("SELECT bot_id, player_color FROM games WHERE player_id = ? AND status = 'finished' AND bot_id IS NOT NULL", (player,))
    stats = await database.get_player_value(player, "endgame_stats", {})
    return dict(lessons_done={r["lesson_id"] for r in lessons}, solved_puzzle_ids={r["puzzle_id"] for r in puzzles},
                finished_games=[(r["bot_id"], r["player_color"]) for r in games], endgame_stats=stats)


async def _progress(player: str, plan: dict) -> dict:
    return with_progress(plan, **await _records(player))


async def _read(player: str, plan_id: str) -> dict:
    row = await database.fetch_one("SELECT id, created_at, plan_json FROM player_plans WHERE id = ? AND player_id = ?", (plan_id, player))
    if not row:
        raise HTTPException(404, "no such plan")
    return {"id": row["id"], "created_at": row["created_at"], **json.loads(row["plan_json"])}


@router.post("")
async def create_plan(req: PlanRequest, player: Player) -> dict:
    """The plan for a goal, stored; or no plan and the closest opening families when nothing matches."""
    started = time.monotonic()
    plan = await asyncio.to_thread(build_plan, req.goal.strip(), await player_level(player))
    ms = (time.monotonic() - started) * 1000
    if plan is None:
        LOGGER.info("plan: no match for %r (%.0fms)", req.goal, ms)
        return {"plan": None, "closest": closest_families(req.goal),
                "message": "Nothing in the lessons, courses, puzzles, games or endgames matches that goal. Name an opening, a phase (endgames, middlegames) or a theme (rook endgames, attacking the king)."}
    plan_id = uuid.uuid4().hex[:12]
    await database.execute("INSERT INTO player_plans(id, player_id, goal, plan_json) VALUES(?, ?, ?, ?)", (plan_id, player, req.goal.strip(), json.dumps(plan)))
    LOGGER.info("plan %s: %d steps from %s (%.0fms)", plan_id, len(plan["steps"]), plan["sources"], ms)
    return {"plan": await _progress(player, await _read(player, plan_id)), "closest": [], "message": None}


@router.get("")
async def list_plans(player: Player) -> dict:
    rows = await database.fetch_all("SELECT id, created_at, plan_json FROM player_plans WHERE player_id = ? ORDER BY created_at DESC, rowid DESC", (player,))
    records = await _records(player) if rows else {}
    out = []
    for r in rows:
        plan = with_progress({"id": r["id"], "created_at": r["created_at"], **json.loads(r["plan_json"])}, **records)
        out.append({k: plan[k] for k in ("id", "created_at", "goal", "title", "done", "total")})
    return {"plans": out}


@router.get("/{plan_id}")
async def get_plan(plan_id: str, player: Player) -> dict:
    return {"plan": await _progress(player, await _read(player, plan_id))}


@router.post("/{plan_id}/steps/{n}")
async def tick_step(plan_id: str, n: int, req: StepTick, player: Player) -> dict:
    """Marks a step the store cannot see (a course line, a book line, a master game) done by hand."""
    async with _PLAN_LOCKS[plan_id]:  # read, change and write as one, so a second quick tick does not undo the first
        plan = await _read(player, plan_id)
        step = next((s for s in plan["steps"] if s["n"] == n), None)
        if step is None:
            raise HTTPException(404, f"plan {plan_id} has no step {n}")
        if step["kind"] in TRACKED_KINDS:
            raise HTTPException(409, f"step {n} is a {step['kind']}: its progress comes from your records, not a tick")
        ticked = set(plan.get("ticked", []))
        (ticked.add if req.done else ticked.discard)(n)
        plan["ticked"] = sorted(ticked)
        stored = {k: v for k, v in plan.items() if k not in ("id", "created_at")}
        await database.execute("UPDATE player_plans SET plan_json = ? WHERE id = ? AND player_id = ?", (json.dumps(stored), plan_id, player))
    return {"plan": await _progress(player, plan)}


@router.delete("/{plan_id}")
async def delete_plan(plan_id: str, player: Player) -> dict:
    await _read(player, plan_id)
    await database.execute("DELETE FROM player_plans WHERE id = ? AND player_id = ?", (plan_id, player))
    return {"deleted": True}
