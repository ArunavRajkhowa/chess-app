"""Learn API: the curriculum tree, one lesson's sections, the learner's progress, and the engine
reply for drill sections (play a position against the computer with a goal)."""
from __future__ import annotations

import json

import chess
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..content.lessons import BANDS, find_lesson, load_curriculum
from ..engine.pool import pool
from ..storage.db import database

router = APIRouter(prefix="/api/learn", tags=["learn"])
DRILL_DEPTH = 10


class ProgressUpdate(BaseModel):
    lesson_id: str
    completed: bool = False
    score: float | None = Field(None, ge=0, le=100)
    state: dict = Field(default_factory=dict)


class DrillMove(BaseModel):
    fen: str
    move: str
    goal: str = Field(pattern="^(mate|promote|draw|survive|win_material)$")
    depth: int = Field(DRILL_DEPTH, ge=1, le=20)
    start_fen: str | None = Field(None, description="the drill's first position; needed for win_material")


PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


def _material_balance(board: chess.Board, color: chess.Color) -> int:
    return sum(v * (len(board.pieces(pt, color)) - len(board.pieces(pt, not color))) for pt, v in PIECE_VALUES.items())


@router.get("/curriculum")
async def curriculum() -> dict:
    modules = load_curriculum()
    progress = {r["lesson_id"]: r for r in await database.fetch_all("SELECT lesson_id, completed_at, score, attempts FROM lesson_progress")}
    bands = []
    for b in BANDS:
        mods = [m for m in modules if m.band == b["band"]]
        lessons_total = sum(len(m.lessons) for m in mods)
        done = sum(1 for m in mods for lsn in m.lessons if progress.get(lsn.id, {}).get("completed_at"))
        bands.append({
            **b, "modules": [
                {"id": m.id, "title": m.title, "strand": m.strand, "summary": m.summary, "source": m.source,
                 "lessons": [{**lsn.summary(), "completed": bool(progress.get(lsn.id, {}).get("completed_at")), "score": progress.get(lsn.id, {}).get("score")} for lsn in m.lessons]}
                for m in mods
            ],
            "lessons_total": lessons_total, "lessons_done": done,
        })
    return {"bands": bands}


@router.get("/lessons/{lesson_id}")
async def lesson(lesson_id: str) -> dict:
    lsn = find_lesson(lesson_id)
    if not lsn:
        raise HTTPException(404, "no such lesson")
    modules = load_curriculum()
    flat = [l for m in modules for l in m.lessons]
    idx = next(i for i, l in enumerate(flat) if l.id == lesson_id)
    return {
        "id": lsn.id, "title": lsn.title, "objective": lsn.objective, "minutes": lsn.minutes, "band": lsn.band, "strand": lsn.strand,
        "module_id": lsn.module_id, "sections": lsn.sections,
        "prev": flat[idx - 1].id if idx > 0 else None, "next": flat[idx + 1].id if idx + 1 < len(flat) else None,
    }


@router.get("/progress")
async def progress() -> dict:
    rows = await database.fetch_all("SELECT lesson_id, completed_at, score, attempts, state_json FROM lesson_progress")
    return {"progress": {r["lesson_id"]: {"completed_at": r["completed_at"], "score": r["score"], "attempts": r["attempts"], "state": json.loads(r["state_json"])} for r in rows}}


@router.post("/progress")
async def update_progress(req: ProgressUpdate) -> dict:
    if not find_lesson(req.lesson_id):
        raise HTTPException(404, "no such lesson")
    await database.execute(
        "INSERT INTO lesson_progress(lesson_id, completed_at, score, attempts, state_json) VALUES(?, CASE WHEN ? THEN datetime('now') END, ?, 1, ?) "
        "ON CONFLICT(lesson_id) DO UPDATE SET completed_at = COALESCE(CASE WHEN excluded.completed_at IS NOT NULL THEN excluded.completed_at END, lesson_progress.completed_at), "
        "score = COALESCE(excluded.score, lesson_progress.score), attempts = lesson_progress.attempts + 1, state_json = excluded.state_json",
        (req.lesson_id, int(req.completed), req.score, json.dumps(req.state)),
    )
    return {"ok": True}


@router.post("/drill/move")
async def drill_move(req: DrillMove) -> dict:
    """Applies the learner's move, checks the goal, and answers with the engine's reply."""
    try:
        board = chess.Board(req.fen)
    except ValueError:
        raise HTTPException(400, f"bad FEN {req.fen!r}")
    if not board.is_valid():
        raise HTTPException(400, f"illegal position {req.fen!r}")
    try:
        move = chess.Move.from_uci(req.move)
    except ValueError:
        try:
            move = board.parse_san(req.move)
        except ValueError:
            raise HTTPException(400, f"cannot read move {req.move!r} as UCI or SAN")
    if move not in board.legal_moves:
        raise HTTPException(400, f"illegal move {req.move}")
    learner = board.turn
    start_balance = None
    if req.goal == "win_material":
        try:
            start_balance = _material_balance(chess.Board(req.start_fen or req.fen), learner)
        except ValueError:
            raise HTTPException(400, "bad start_fen")
    san = board.san(move)
    board.push(move)
    outcome = _outcome(board, learner, req.goal, move, start_balance)
    reply = None
    if outcome is None and not board.is_game_over(claim_draw=True):
        infos = await pool.analyse(board, depth=req.depth, slot="play")
        rm = infos[0]["pv"][0]
        reply = {"san": board.san(rm), "uci": rm.uci()}
        board.push(rm)
        outcome = _outcome(board, learner, req.goal, None, start_balance)
    return {"fen": board.fen(), "played": san, "reply": reply, "outcome": outcome}


def _outcome(board: chess.Board, learner: chess.Color, goal: str, learner_move: chess.Move | None,
             start_balance: int | None = None) -> dict | None:
    if board.is_checkmate():
        won = board.turn != learner
        return {"result": "success" if (won and goal in ("mate", "win_material", "survive")) else "fail", "reason": "checkmate" if won else "you were mated"}
    if board.is_stalemate():
        return {"result": "success" if goal in ("draw", "survive") else "fail", "reason": "stalemate"}
    if board.is_insufficient_material() or board.can_claim_threefold_repetition() or board.can_claim_fifty_moves():
        return {"result": "success" if goal in ("draw", "survive") else "fail", "reason": "draw"}
    if goal == "promote" and learner_move is not None and learner_move.promotion:
        return {"result": "success", "reason": "promoted"}
    if goal == "win_material" and start_balance is not None and learner_move is None:
        gained = _material_balance(board, learner) - start_balance
        if gained >= 1:
            return {"result": "success", "reason": f"won material (+{gained})"}
        if gained <= -3:
            return {"result": "fail", "reason": f"lost material ({gained})"}
    return None
