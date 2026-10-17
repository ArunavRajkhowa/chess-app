"""Coach API: explanations, hints and chat grounded in the position fact sheet. Responses stream as
server-sent events so the text appears as it is written; the final event says whether the model
or the rule-based fallback answered."""
from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator

import chess
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..coach import fallback
from ..coach.client import CoachDeclined, llm_enabled, llm_model, prompt, stream_text
from ..coach.facts import position_facts
from ..engine.pool import pool
from ..review import jobs
from ..review.classify import BLUNDER, MISS, MISTAKE
from ..storage import games as store

LOGGER = logging.getLogger("chess.coach.api")
router = APIRouter(prefix="/api/coach", tags=["coach"])

Level = str
_SAN_TOKEN = re.compile(r"\b(?:O-O(?:-O)?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?)\b")


class ExplainRequest(BaseModel):
    game_id: str
    ply: int = Field(ge=1)
    level: Level = Field("intermediate", pattern="^(beginner|intermediate|advanced|master)$")


class ChatRequest(BaseModel):
    fen: str
    question: str = Field(min_length=1, max_length=2000)
    level: Level = Field("intermediate", pattern="^(beginner|intermediate|advanced|master)$")
    history: list[dict] = Field(default_factory=list, description="prior turns [{role, content}]")


class HintRequest(BaseModel):
    fen: str
    hint_level: int = Field(1, ge=1, le=3)
    level: Level = "intermediate"


class SummaryRequest(BaseModel):
    game_id: str
    level: Level = "intermediate"


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


# A bare square ("the pawn on e4") reads like a pawn move, so a two-character token counts as a
# move only after a move number ("12.e5").
_NUMBERED_PAWN_MOVE = re.compile(r"\d+\.(?:\.\.)?\s?([a-h][1-8])\b")


def _with_lines(board: chess.Board, facts: dict) -> list[chess.Board]:
    """The position and every position along the fact sheet's engine lines, so a move the model
    quotes from a line counts as verified."""
    boards = [board]
    for c in facts.get("candidate_moves", []):
        b = board.copy()
        for san in c["line"]:
            try:
                b.push_san(san)
            except ValueError:
                break
            boards.append(b.copy())
    return boards


def _unverified_moves(text: str, boards: list[chess.Board]) -> list[str]:
    """Move tokens in the text that are legal in none of the given positions."""
    legal: set[str] = set()
    for b in boards:
        for mv in b.legal_moves:
            legal.add(b.san(mv).rstrip("+#"))
    tokens = {t for t in _SAN_TOKEN.findall(text) if len(t) >= 3} | set(_NUMBERED_PAWN_MOVE.findall(text))
    return sorted(t for t in tokens if t.rstrip("+#") not in legal and re.search(r"[a-h][1-8]", t))


async def _respond(system: str, user: str, purpose: str, rules_text: str, boards: list[chess.Board]) -> AsyncIterator[str]:
    if llm_enabled():
        collected: list[str] = []
        try:
            async for chunk in stream_text(system=system, user=user, purpose=purpose):
                collected.append(chunk)
                yield _sse({"type": "text", "text": chunk})
            text = "".join(collected)
            yield _sse({"type": "done", "source": "llm", "model": llm_model(), "unverified_moves": _unverified_moves(text, boards)})
            return
        except CoachDeclined:
            LOGGER.warning("coach declined %s; using rules", purpose)
        except Exception:  # boundary: the stream must end with an answer, never hang
            LOGGER.error("coach model call failed for %s; using rules", purpose, exc_info=True)
            if collected:
                yield _sse({"type": "text", "text": "\n\n(The coach stopped early.)"})
                yield _sse({"type": "done", "source": "llm", "model": llm_model()})
                return
    yield _sse({"type": "text", "text": rules_text})
    yield _sse({"type": "done", "source": "rules"})


def _stream(gen: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(gen, media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/facts")
async def facts(fen: str) -> dict:
    try:
        board = chess.Board(fen)
    except ValueError:
        raise HTTPException(400, f"bad FEN {fen!r}")
    if not board.is_valid():
        raise HTTPException(400, f"illegal position {fen!r}")
    return await position_facts(board, pool)


@router.post("/explain")
async def explain(req: ExplainRequest):
    row = await store.read_game(req.game_id)
    if not row:
        raise HTTPException(404, "no such game")
    report = await jobs.stored_report(req.game_id)
    if not report or req.ply > len(report["moves"]):
        raise HTTPException(409, "review this game first")
    rm = report["moves"][req.ply - 1]
    before = chess.Board(rm["fen_before"])
    after = chess.Board(rm["fen_after"])
    facts_before = await position_facts(before, pool)
    facts_after = await position_facts(after, pool, last_move=chess.Move.from_uci(rm["uci"]))
    mover = rm["color"]
    user = prompt("explain_move").format(
        player_level=req.level, move_san=rm["san"], mover=mover, classification=rm["classification"],
        best_san=rm["best_move_san"], best_eval=rm["best_eval_text"], best_line=" ".join(rm["best_line_san"]),
        eval_before=rm["best_eval_text"], eval_after=rm["eval_after_text"], win_before=rm["win_before"], win_after=rm["win_after"],
        facts_before=json.dumps(facts_before), facts_after=json.dumps(facts_after),
    )
    rules = fallback.explain_move_text(
        move_san=rm["san"], mover=mover, classification=rm["classification"], best_san=rm["best_move_san"],
        best_line=rm["best_line_san"], eval_before=rm["best_eval_text"], eval_after=rm["eval_after_text"],
        facts_before=facts_before, facts_after=facts_after, level=req.level,
    )
    return _stream(_respond(prompt("coach_system"), user, "explain", rules, _with_lines(before, facts_before) + _with_lines(after, facts_after)))


@router.post("/chat")
async def chat(req: ChatRequest):
    try:
        board = chess.Board(req.fen)
    except ValueError:
        raise HTTPException(400, f"bad FEN {req.fen!r}")
    if not board.is_valid():
        raise HTTPException(400, f"illegal position {req.fen!r}")
    f = await position_facts(board, pool)
    history = "\n".join(f"{t.get('role', 'user')}: {t.get('content', '')}" for t in req.history[-8:])
    user = prompt("chat").format(player_level=req.level, facts=json.dumps(f))
    if history:
        user += f"\n\nEarlier in this conversation:\n{history}"
    user += f"\n\nQuestion: {req.question}"
    rules = fallback.chat_text(f, req.question, req.level)
    return _stream(_respond(prompt("coach_system"), user, "chat", rules, _with_lines(board, f)))


@router.post("/hint")
async def hint(req: HintRequest):
    try:
        board = chess.Board(req.fen)
    except ValueError:
        raise HTTPException(400, f"bad FEN {req.fen!r}")
    if not board.is_valid():
        raise HTTPException(400, f"illegal position {req.fen!r}")
    f = await position_facts(board, pool)
    user = prompt("hint").format(player_level=req.level, hint_level=req.hint_level, facts=json.dumps(f))
    rules = fallback.hint_text(f, req.hint_level)
    return _stream(_respond(prompt("coach_system"), user, "hint", rules, _with_lines(board, f)))


@router.post("/summary")
async def summary(req: SummaryRequest):
    row = await store.read_game(req.game_id)
    if not row:
        raise HTTPException(404, "no such game")
    report = await jobs.stored_report(req.game_id)
    if not report:
        raise HTTPException(409, "review this game first")
    key = [
        {"move_number": m["move_number"], "color": m["color"], "san": m["san"], "classification": m["classification"],
         "best": m["best_move_san"], "win_before": m["win_before"], "win_after": m["win_after"], "note": m["note"]}
        for m in report["moves"] if m["is_key_moment"]
    ]
    data = {
        "result": report["result"], "opening": report["opening"], "white": report["white"], "black": report["black"],
        "key_moments": key, "player_color": row["player_color"],
    }
    user = prompt("review_summary").format(player_level=req.level, player_color=row["player_color"], summary=json.dumps(data))
    rules = _rules_summary(report, row["player_color"])
    boards = [chess.Board(m["fen_before"]) for m in report["moves"] if m["is_key_moment"]]
    return _stream(_respond(prompt("coach_system"), user, "summary", rules, boards))


def _rules_summary(report: dict, player_color: str) -> str:
    me = report[player_color]
    opp = report["black" if player_color == "white" else "white"]
    errors = [m for m in report["moves"] if m["color"] == player_color and m["classification"] in (MISTAKE, MISS, BLUNDER)]
    worst = sorted(errors, key=lambda m: m["win_before"] - m["win_after"], reverse=True)[:2]
    head = f"You played the {report['opening']['name']}" if report.get("opening") else "You played this game"
    if me["accuracy"] is not None:  # a side with no moves has no accuracy: say nothing rather than a number
        head += f" with {me['accuracy']}% accuracy" + (f" against {opp['accuracy']}%" if opp["accuracy"] is not None else "")
    parts = [head + "."]
    for m in worst:
        parts.append(f"Move {m['move_number']} {m['san']} was a {m['classification']}; {m['best_move_san']} was better.")
    phases = {k: v for k, v in me["phase_accuracy"].items() if v is not None}
    if len(phases) >= 2:
        best = max(phases, key=phases.get)
        weak = min(phases, key=phases.get)
        parts.append(f"Your strongest phase was the {best} ({phases[best]}%), your weakest the {weak} ({phases[weak]}%).")
    return " ".join(parts)
