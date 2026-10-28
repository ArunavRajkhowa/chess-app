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
from ..coach.client import CoachDeclined, CoachTruncated, llm_enabled, llm_model, prompt, stream_text
from ..coach.context import bot_brief, coach_context, player_context
from ..coach.facts import position_facts
from ..engine.pool import pool
from ..settings import settings
from ..openings.book import load_book
from ..review import jobs
from ..review.classify import BLUNDER, MISS, MISTAKE
from ..review.report import review_moves
from ..study.reasons import opponent_to_move, parried_threat
from .learn import material_balance
from ..storage import games as store
from .account import Player

LOGGER = logging.getLogger("chess.coach.api")
router = APIRouter(prefix="/api/coach", tags=["coach"])

Level = str
LEVELS = "^(beginner|intermediate|advanced|master)$"
DEFAULT_LEVEL = "intermediate"
_SAN_TOKEN = re.compile(r"\b(?:O-O(?:-O)?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?)\b")
TRY_DEPTH = 14
MAX_ASKED_MOVES = 3  # a question naming more moves than this is not about particular moves
_SQUARE = re.compile(r"\b([a-h][1-8])\b")
_PIECE_WORDS = {"knight": chess.KNIGHT, "bishop": chess.BISHOP, "rook": chess.ROOK, "queen": chess.QUEEN, "king": chess.KING, "pawn": chess.PAWN}


class ExplainRequest(BaseModel):
    game_id: str
    ply: int = Field(ge=1)
    level: Level | None = Field(None, pattern=LEVELS, description="omitted: from the player's puzzle rating")


# a turn holds at most one answer: COACH_MAX_TOKENS at ~4 characters a token, doubled (a guess)
MAX_TURN_CHARS = settings.COACH_MAX_TOKENS * 8
HISTORY_TURNS = 8  # earlier turns the model sees


class ChatTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=MAX_TURN_CHARS)


class ChatRequest(BaseModel):
    fen: str
    question: str = Field(min_length=1, max_length=2000)
    level: Level | None = Field(None, pattern=LEVELS, description="omitted: from the player's puzzle rating")
    history: list[ChatTurn] = Field(default_factory=list, description="earlier turns; the model sees the last HISTORY_TURNS")
    game_id: str | None = Field(None, description="the game the position comes from: the coach then knows the moves so far")
    lesson_id: str | None = Field(None, description="the lesson the question comes from")


class HintRequest(BaseModel):
    fen: str
    hint_level: int = Field(1, ge=1, le=3)
    level: Level | None = Field(None, pattern=LEVELS)
    game_id: str | None = None


class SummaryRequest(BaseModel):
    game_id: str
    level: Level | None = Field(None, pattern=LEVELS)


def level_of(requested: str | None, context: dict) -> str:
    """The wording level: the one asked for, else the one the player's puzzle rating says, else intermediate."""
    return requested or context["player"].get("level") or DEFAULT_LEVEL


def _game_moves(context: dict) -> tuple[chess.Move | None, str | None, set[str]]:
    """The game's last move, the position before it and the SAN of every move played so far, taken out
    of the context: the facts carry the move, and a move quoted from the game counts as verified."""
    game = context.get("game") or {}
    uci, fens, played = game.pop("last_move_uci", None), game.pop("positions", []), game.pop("played", [])
    previous_fen = fens[-2] if uci and len(fens) >= 2 else None
    return (chess.Move.from_uci(uci) if uci else None), previous_fen, {san.rstrip("+#") for san in played}


class TryRequest(BaseModel):
    fen: str
    move: str = Field(description="the move the learner tries, UCI")
    compare: str | None = Field(None, description="UCI of the move it is measured against: the game move or the solution")


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


# A bare square ("the pawn on e4") reads like a pawn move, so a two-character token counts as a
# move only after a move number ("12.e5").
_NUMBERED_PAWN_MOVE = re.compile(r"\d+\.(?:\.\.)?\s?([a-h][1-8])\b")


def _legal_sans(board: chess.Board) -> set[str]:
    return {board.san(mv).rstrip("+#") for mv in board.legal_moves}


def _line_sans(start: chess.Board, line: list[str]) -> set[str]:
    """The moves of a line that replay legally from its start position."""
    b, out = start.copy(), set()
    for san in line:
        try:
            mv = b.parse_san(san)
        except ValueError:
            break
        out.add(b.san(mv).rstrip("+#"))
        b.push(mv)
    return out


def _verified(board: chess.Board, facts: dict) -> set[str]:
    """Moves the model may name: legal in the position, or in a fact sheet line."""
    sans = _legal_sans(board)
    lines = [(board, c["line"]) for c in facts.get("candidate_moves", [])]
    if facts.get("book"):
        lines.append((board, facts["book"]["main_line"]))
    other = opponent_to_move(board)
    if other.is_valid():  # the opponent's threats and pawn breaks are moves of the side not to move
        if facts.get("opponent_threat"):
            lines.append((other, facts["opponent_threat"]["line"]))
        lines += [(other, [t["san"]]) for t in facts.get("threats_against_side_to_move", [])]
        lines += [(other, [p]) for p in (facts.get("black" if board.turn == chess.WHITE else "white") or {}).get("pawn_breaks", [])]
    for start, line in lines:
        sans |= _line_sans(start, line)
    return sans


def _parried(previous: chess.Board | None, last_move: chess.Move | None) -> set[str]:
    """The threat the last move parried, which the fact sheet names: the one move of the previous position allowed."""
    threat = parried_threat(previous, last_move) if previous and last_move in previous.legal_moves else None
    return {threat["san"].rstrip("+#")} if threat else set()


def _unverified_moves(text: str, verified: set[str]) -> list[str]:
    """Move tokens in the text that are not in the verified set."""
    tokens = {t for t in _SAN_TOKEN.findall(text) if len(t) >= 3} | set(_NUMBERED_PAWN_MOVE.findall(text))
    return sorted(t for t in tokens if t.rstrip("+#") not in verified)


async def _respond(system: str, user: str, purpose: str, rules_text: str, verified: set[str]) -> AsyncIterator[str]:
    if llm_enabled():
        collected: list[str] = []
        try:
            async for chunk in stream_text(system=system, user=user, purpose=purpose):
                collected.append(chunk)
                yield _sse({"type": "text", "text": chunk})
            text = "".join(collected)
            yield _sse({"type": "done", "source": "llm", "model": llm_model(), "unverified_moves": _unverified_moves(text, verified)})
            return
        except CoachDeclined:
            LOGGER.warning("coach declined %s", purpose)
        except CoachTruncated as exc:
            LOGGER.warning("coach answer cut for %s: %s", purpose, exc)
        except Exception:  # boundary: the stream must end with an answer, never hang
            LOGGER.error("coach model call failed for %s", purpose, exc_info=True)
        if collected:  # model text is on screen: end it, check it, and add no rules text
            yield _sse({"type": "text", "text": "\n\n(The coach stopped early.)"})
            yield _sse({"type": "done", "source": "llm", "model": llm_model(), "unverified_moves": _unverified_moves("".join(collected), verified)})
            return
    yield _sse({"type": "text", "text": rules_text})
    yield _sse({"type": "done", "source": "rules"})


def _position(fen: str) -> chess.Board:
    try:
        board = chess.Board(fen)
    except ValueError:
        raise HTTPException(400, f"bad FEN {fen!r}")
    if not board.is_valid():
        raise HTTPException(400, f"illegal position {fen!r}")
    return board


def _legal(board: chess.Board, uci: str, field: str) -> chess.Move:
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        raise HTTPException(400, f"{field} {uci!r} is not a UCI move")
    if move not in board.legal_moves:
        raise HTTPException(400, f"{field} {uci!r} is illegal in {board.fen()!r}")
    return move


def numbered(board: chess.Board, sans: list[str]) -> str:
    """SAN with move numbers from the given position, as a book prints a line: "6.d4 b5 7.Bb3"."""
    b, out = board.copy(), []
    for i, san in enumerate(sans):
        out.append(f"{b.fullmove_number}.{san}" if b.turn == chess.WHITE else f"{b.fullmove_number}...{san}" if i == 0 else san)
        b.push_san(san)
    return " ".join(out)


async def judge_move(board: chess.Board, move: chess.Move) -> dict:
    """One move judged as the review judges it, the engine's answer to it, and the book name it reaches."""
    rm = (await review_moves([move], pool, depth=TRY_DEPTH, start_fen=board.fen())).moves[0]
    after = board.copy()
    after.push(move)
    facts_after = await position_facts(after, pool, depth=TRY_DEPTH, last_move=move)
    reply_line = facts_after["candidate_moves"][0]["line"] if facts_after["candidate_moves"] else []
    end = after.copy()
    for san in reply_line:
        end.push_san(san)
    opening = load_book().lookup(after)
    return {
        "san": rm.san, "uci": rm.uci, "classification": rm.classification, "eval_after": rm.eval_after_text,
        "win_before": rm.win_before, "win_after": rm.win_after,
        "best_san": rm.best_move_san, "best_uci": rm.best_move_uci, "best_eval": rm.best_eval_text,
        "reply_line": reply_line, "reply_text": numbered(after, reply_line),
        "material_after_reply": material_balance(end, chess.WHITE),  # White minus Black, in pawns, at the end of the answer
        "opening": {"eco": opening.eco, "name": opening.name} if opening else None,
        "explanation": fallback.explain_move_text(
            move_san=rm.san, mover=rm.color, classification=rm.classification, best_san=rm.best_move_san,
            best_line=rm.best_line_san, eval_before=rm.best_eval_text, eval_after=rm.eval_after_text,
            facts_before={"candidate_moves": []}, facts_after=facts_after, level="intermediate",  # the answer travels as reply_line
        ),
    }


def asked_moves(board: chess.Board, question: str) -> list[chess.Move]:
    """Legal moves a question names: SAN ("why not Nxe4?") or a piece and a square ("why didn't the knight take e4?")."""
    legal = list(board.legal_moves)
    by_san = {board.san(m).rstrip("+#"): m for m in legal}
    # a bare square ("e4") reads like a pawn move, so SAN counts from three characters
    named = list(dict.fromkeys(by_san[t.rstrip("+#")] for t in _SAN_TOKEN.findall(question) if len(t) >= 3 and t.rstrip("+#") in by_san))
    if named:
        return named[:MAX_ASKED_MOVES]
    text = question.lower()
    squares = {chess.parse_square(sq) for sq in _SQUARE.findall(text)}
    pieces = {pt for word, pt in _PIECE_WORDS.items() if word in text}
    hits = [m for m in legal if m.to_square in squares and (not pieces or board.piece_type_at(m.from_square) in pieces)]
    return hits if len(hits) <= MAX_ASKED_MOVES else []


def _after_lines(board: chess.Board, judged: list[dict]) -> set[str]:
    """The moves of each judged move and the engine's answer to it, for the move check."""
    return set().union(*(_line_sans(board, [j["san"], *j["reply_line"]]) for j in judged))


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
async def explain(req: ExplainRequest, player: Player):
    row = await store.read_game(player, req.game_id)
    if not row:
        raise HTTPException(404, "no such game")
    report = await jobs.stored_report(player, req.game_id)
    if not report or req.ply > len(report["moves"]):
        raise HTTPException(409, "review this game first")
    rm = report["moves"][req.ply - 1]
    before = chess.Board(rm["fen_before"])
    after = chess.Board(rm["fen_after"])
    context = await coach_context(player, before, game_id=req.game_id, ply=req.ply - 1)
    _, _, played = _game_moves(context)
    level = level_of(req.level, context)
    facts_before = await position_facts(before, pool)
    facts_after = await position_facts(after, pool, last_move=chess.Move.from_uci(rm["uci"]), previous_fen=rm["fen_before"])
    mover = rm["color"]
    user = prompt("explain_move").format(
        player_level=level, context=json.dumps(context), move_san=rm["san"], mover=mover, classification=rm["classification"],
        best_san=rm["best_move_san"], best_eval=rm["best_eval_text"], best_line=" ".join(rm["best_line_san"]),
        eval_before=rm["best_eval_text"], eval_after=rm["eval_after_text"], win_before=rm["win_before"], win_after=rm["win_after"],
        facts_before=json.dumps(facts_before), facts_after=json.dumps(facts_after),
    )
    rules = fallback.explain_move_text(
        move_san=rm["san"], mover=mover, classification=rm["classification"], best_san=rm["best_move_san"],
        best_line=rm["best_line_san"], eval_before=rm["best_eval_text"], eval_after=rm["eval_after_text"],
        facts_before=facts_before, facts_after=facts_after, level=level,
    )
    move = chess.Move.from_uci(rm["uci"])
    verified = _verified(before, facts_before) | _verified(after, facts_after) | _parried(before, move) | _line_sans(before, rm["best_line_san"]) | played
    return _stream(_respond(prompt("coach_system"), user, "explain", rules, verified))


async def chat_answer(board: chess.Board, question: str, *, level: str, context: dict, history: list[ChatTurn] = ()) -> tuple[str, str, set[str]]:
    """The model's user prompt, the rule-based answer and the moves the answer may name."""
    last_move, previous_fen, played = _game_moves(context)
    f = await position_facts(board, pool, last_move=last_move, previous_fen=previous_fen)
    asked = [await judge_move(board, m) for m in asked_moves(board, question)]
    if asked:
        f["asked_moves"] = asked
    turns = "\n".join(f"{t.role}: {t.content}" for t in list(history)[-HISTORY_TURNS:])
    user = prompt("chat").format(player_level=level, context=json.dumps(context), facts=json.dumps(f))
    if turns:
        user += f"\n\nEarlier in this conversation:\n{turns}"
    user += f"\n\nQuestion: {question}"
    f["context"] = context
    previous = chess.Board(previous_fen) if previous_fen else None
    if previous and last_move in previous.legal_moves:
        played = played | {previous.san(last_move).rstrip("+#")}  # the move just played is a fact the sheet carries
    return user, fallback.chat_text(f, question, level), _verified(board, f) | _parried(previous, last_move) | _after_lines(board, asked) | played


@router.post("/chat")
async def chat(req: ChatRequest, player: Player):
    board = _position(req.fen)
    context = await coach_context(player, board, game_id=req.game_id, lesson_id=req.lesson_id)
    level = level_of(req.level, context)
    user, rules, verified = await chat_answer(board, req.question, level=level, context=context, history=req.history)
    return _stream(_respond(prompt("coach_system"), user, "chat", rules, verified))


@router.post("/try")
async def try_move(req: TryRequest) -> dict:
    """The learner's move judged against the engine, with the engine's answer; `compare` judges a second move the same way."""
    board = _position(req.fen)
    tried = await judge_move(board, _legal(board, req.move, "move"))
    compare = None
    if req.compare and req.compare != req.move:
        compare = await judge_move(board, _legal(board, req.compare, "compare"))
    return {"tried": tried, "compare": compare}


@router.post("/hint")
async def hint(req: HintRequest, player: Player):
    board = _position(req.fen)
    context = await coach_context(player, board, game_id=req.game_id)
    last_move, previous_fen, played = _game_moves(context)
    level = level_of(req.level, context)
    f = await position_facts(board, pool, last_move=last_move, previous_fen=previous_fen)
    user = prompt("hint").format(player_level=level, hint_level=req.hint_level, context=json.dumps(context), facts=json.dumps(f))
    rules = fallback.hint_text(f, req.hint_level)
    previous = chess.Board(previous_fen) if previous_fen else None
    return _stream(_respond(prompt("coach_system"), user, "hint", rules, _verified(board, f) | _parried(previous, last_move) | played))


@router.post("/summary")
async def summary(req: SummaryRequest, player: Player):
    row = await store.read_game(player, req.game_id)
    if not row:
        raise HTTPException(404, "no such game")
    report = await jobs.stored_report(player, req.game_id)
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
    context = {"player": await player_context(player), "bot": bot_brief(row.get("bot_id")), "time_control": row.get("time_control")}
    level = level_of(req.level, context)
    user = prompt("review_summary").format(player_level=level, player_color=row["player_color"], context=json.dumps(context), summary=json.dumps(data))
    rules = _rules_summary(report, row["player_color"])
    verified = set().union(*(_legal_sans(chess.Board(m["fen_before"])) for m in report["moves"] if m["is_key_moment"]))
    return _stream(_respond(prompt("coach_system"), user, "summary", rules, verified))


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
