"""Learn API: the curriculum tree, one lesson's sections, the learner's progress, the spaced review
queue of missed tasks, and the engine reply for drill sections (play a position against the computer
with a goal)."""
from __future__ import annotations

import chess
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..content.lessons import BANDS, TASK_TYPES, find_lesson, load_curriculum
from ..engine.pool import pool
from ..puzzles.glicko import Rating
from ..puzzles.store import THEME_INFO, load_library
from ..storage.db import database
from .account import Player
from .puzzles import RATING_KEY, due_puzzles

router = APIRouter(prefix="/api/learn", tags=["learn"])
DRILL_DEPTH = 10
# Spaced review, the ladder Chessable's MoveTrainer and SM-2 use: a missed task comes back tomorrow,
# and every pass at review roughly doubles the gap. A miss at review starts the ladder again.
REVIEW_LADDER_DAYS = (1, 3, 7, 16, 35, 90)
SETTLED_RD = 200  # a Glicko rating deviation this low means enough rated puzzles to place the player


class ProgressUpdate(BaseModel):
    lesson_id: str
    completed: bool = False
    score: float | None = Field(None, ge=0, le=100)
    results: dict[int, bool] = Field(default_factory=dict, description="section index -> solved on the first try")


class ReviewResult(BaseModel):
    solved: bool


class DrillMove(BaseModel):
    fen: str
    move: str
    goal: str = Field(pattern="^(mate|promote|draw|survive|win_material)$")
    depth: int = Field(DRILL_DEPTH, ge=1, le=20)
    start_fen: str | None = Field(None, description="the drill's first position; needed for win_material")
    history: list[str] = Field(default_factory=list, max_length=400, description="UCI moves from start_fen to fen; lets a repetition count")


PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


def material_balance(board: chess.Board, color: chess.Color) -> int:
    return sum(v * (len(board.pieces(pt, color)) - len(board.pieces(pt, not color))) for pt, v in PIECE_VALUES.items())


def band_for_rating(rating: float) -> int:
    """The band whose rating range holds a puzzle rating; band 0 is the rules and never suggested."""
    return next((b["band"] for b in BANDS if b["max_rating"] is not None and rating < b["max_rating"]), BANDS[-1]["band"])


async def player_level(player: str) -> dict | None:
    """The band the player's puzzle rating places them in, or None until the rating has settled."""
    d = await database.get_player_value(player, RATING_KEY, None)
    r = Rating(**d) if d else Rating()
    if r.rd > SETTLED_RD:
        return None
    return {"puzzle_rating": round(r.rating), "band": band_for_rating(r.rating)}


@router.get("/curriculum")
async def curriculum(player: Player) -> dict:
    modules = load_curriculum()
    rows = await database.fetch_all("SELECT lesson_id, completed_at, score, attempts FROM player_lessons WHERE player_id = ?", (player,))
    progress = {r["lesson_id"]: r for r in rows}
    due = await database.fetch_one("SELECT COUNT(*) AS n FROM player_reviews WHERE player_id = ? AND due_at <= datetime('now')", (player,))
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
    puzzles = await due_puzzles(player)
    return {"bands": bands, "review_due": (due["n"] if due else 0) + puzzles["due"], "level": await player_level(player)}


@router.get("/lessons/{lesson_id}")
async def lesson(lesson_id: str) -> dict:
    lsn = find_lesson(lesson_id)
    if not lsn:
        raise HTTPException(404, "no such lesson")
    modules = load_curriculum()
    flat = [l for m in modules for l in m.lessons]
    idx = next(i for i, l in enumerate(flat) if l.id == lesson_id)
    counts = {t: len(load_library().by_theme.get(t, [])) for t in lsn.practice}
    return {
        "id": lsn.id, "title": lsn.title, "objective": lsn.objective, "minutes": lsn.minutes, "band": lsn.band, "strand": lsn.strand,
        "module_id": lsn.module_id, "sections": lsn.sections,
        "practice": [{"key": t, "name": THEME_INFO[t][0], "count": n} for t, n in counts.items() if n],
        "prev": flat[idx - 1].id if idx > 0 else None, "next": flat[idx + 1].id if idx + 1 < len(flat) else None,
    }


@router.get("/progress")
async def progress(player: Player) -> dict:
    rows = await database.fetch_all("SELECT lesson_id, completed_at, score, attempts FROM player_lessons WHERE player_id = ?", (player,))
    return {"progress": {r["lesson_id"]: {"completed_at": r["completed_at"], "score": r["score"], "attempts": r["attempts"]} for r in rows}}


@router.post("/progress")
async def update_progress(req: ProgressUpdate, player: Player) -> dict:
    lsn = find_lesson(req.lesson_id)
    if not lsn:
        raise HTTPException(404, "no such lesson")
    for idx in req.results:
        if not (0 <= idx < len(lsn.sections)) or lsn.sections[idx]["type"] not in TASK_TYPES:
            raise HTTPException(400, f"results index {idx}: lesson {req.lesson_id} has no challenge or quiz there")
    await database.execute(
        "INSERT INTO player_lessons(player_id, lesson_id, completed_at, score, attempts) VALUES(?, ?, CASE WHEN ? THEN datetime('now') END, ?, 1) "
        "ON CONFLICT(player_id, lesson_id) DO UPDATE SET completed_at = COALESCE(CASE WHEN excluded.completed_at IS NOT NULL THEN excluded.completed_at END, player_lessons.completed_at), "
        "score = CASE WHEN excluded.score IS NULL THEN player_lessons.score "
        "WHEN player_lessons.score IS NULL OR excluded.score > player_lessons.score THEN excluded.score ELSE player_lessons.score END, "
        "attempts = player_lessons.attempts + 1",
        (player, req.lesson_id, int(req.completed), req.score),
    )
    # A missed task joins the review queue for tomorrow; a task solved again while already queued climbs the ladder.
    for idx, solved in req.results.items():
        await _reschedule(player, req.lesson_id, idx, solved=solved, only_existing=solved)
    return {"ok": True}


def next_interval(interval_days: int, solved: bool) -> int:
    if not solved:
        return REVIEW_LADDER_DAYS[0]
    return next((d for d in REVIEW_LADDER_DAYS if d > interval_days), REVIEW_LADDER_DAYS[-1])


async def _reschedule(player: str, lesson_id: str, idx: int, *, solved: bool, only_existing: bool = False) -> dict | None:
    row = await database.fetch_one("SELECT interval_days FROM player_reviews WHERE player_id = ? AND lesson_id = ? AND section_index = ?", (player, lesson_id, idx))
    if row is None and only_existing:
        return None
    interval = next_interval(row["interval_days"] if row else 0, solved)
    await database.execute(
        "INSERT INTO player_reviews(player_id, lesson_id, section_index, due_at, interval_days, reps, lapses) VALUES(?, ?, ?, datetime('now', ?), ?, 0, ?) "
        "ON CONFLICT(player_id, lesson_id, section_index) DO UPDATE SET due_at = excluded.due_at, interval_days = excluded.interval_days, "
        "reps = player_reviews.reps + 1, lapses = player_reviews.lapses + excluded.lapses",
        (player, lesson_id, idx, f"+{interval} days", interval, 0 if solved else 1),
    )
    return {"interval_days": interval}


@router.get("/review")
async def review_queue(player: Player) -> dict:
    """The missed tasks due now, oldest first, each with its section so the browser runs it as in the lesson."""
    rows = await database.fetch_all("SELECT lesson_id, section_index, due_at, interval_days FROM player_reviews WHERE player_id = ? ORDER BY due_at", (player,))
    now = (await database.fetch_one("SELECT datetime('now') AS now"))["now"]
    items, later = [], []
    for r in rows:
        lsn = find_lesson(r["lesson_id"])
        if not lsn or r["section_index"] >= len(lsn.sections) or lsn.sections[r["section_index"]]["type"] not in TASK_TYPES:
            continue  # the lesson changed since: nothing to show for this row
        if r["due_at"] <= now:
            items.append({"lesson_id": lsn.id, "lesson_title": lsn.title, "section_index": r["section_index"],
                          "interval_days": r["interval_days"], "section": lsn.sections[r["section_index"]]})
        else:
            later.append(r["due_at"])
    return {"items": items, "later": len(later), "next_due_at": min(later) if later else None}


@router.post("/review/{lesson_id}/{section_index}")
async def review_result(lesson_id: str, section_index: int, req: ReviewResult, player: Player) -> dict:
    out = await _reschedule(player, lesson_id, section_index, solved=req.solved, only_existing=True)
    if out is None:
        raise HTTPException(404, f"no review item for lesson {lesson_id} section {section_index}")
    return out


@router.post("/drill/move")
async def drill_move(req: DrillMove) -> dict:
    """Applies the learner's move, checks the goal, and answers with the engine's reply."""
    try:
        board = chess.Board(req.fen)
        if req.history:  # rebuild the game so far: a threefold repetition needs the earlier positions
            replay = chess.Board(req.start_fen or "")
            for uci in req.history:
                replay.push(replay.parse_uci(uci))
            if replay.fen() != board.fen():
                raise HTTPException(400, f"history leads to {replay.fen()!r}, not fen {req.fen!r}")
            board = replay
    except ValueError:
        raise HTTPException(400, f"bad FEN, start_fen or history (fen {req.fen!r})")
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
            start_balance = material_balance(chess.Board(req.start_fen or req.fen), learner)
        except ValueError:
            raise HTTPException(400, "bad start_fen")
    san = board.san(move)
    board.push(move)
    outcome = drill_outcome(board, learner, req.goal, move, start_balance)
    reply = None
    if outcome is None and not board.is_game_over():
        infos = await pool.analyse(board, depth=req.depth, slot="play")
        rm = infos[0]["pv"][0]
        reply = {"san": board.san(rm), "uci": rm.uci()}
        board.push(rm)
        outcome = drill_outcome(board, learner, req.goal, None, start_balance)
    return {"fen": board.fen(), "played": san, "reply": reply, "outcome": outcome}


def drill_outcome(board: chess.Board, learner: chess.Color, goal: str, learner_move: chess.Move | None,
                  start_balance: int | None = None) -> dict | None:
    """The drill result after one move, or None while it goes on. Shared with the endgame trainer."""
    if board.is_checkmate():
        won = board.turn != learner
        return {"result": "success" if (won and goal in ("mate", "win_material", "survive")) else "fail", "reason": "checkmate" if won else "you were mated"}
    if board.is_stalemate():
        return {"result": "success" if goal in ("draw", "survive") else "fail", "reason": "stalemate"}
    if board.is_insufficient_material() or board.is_repetition(3) or board.is_fifty_moves():
        return {"result": "success" if goal in ("draw", "survive") else "fail", "reason": "draw"}
    if goal == "promote" and learner_move is not None and learner_move.promotion:
        return {"result": "success", "reason": "promoted"}
    if goal == "win_material" and start_balance is not None and learner_move is None:
        gained = material_balance(board, learner) - start_balance
        if gained >= 1:
            return {"result": "success", "reason": f"won material (+{gained})"}
        last = board.peek()
        recapture = last.promotion and any(m.to_square == last.to_square for m in board.legal_moves)
        if gained <= -3 and not recapture:  # a new queen the learner can take is judged after that reply
            return {"result": "fail", "reason": f"lost material ({gained})"}
    return None
