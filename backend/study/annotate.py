"""Study annotations: for every move of a game, why it was played and why the alternatives were
not, from the engine's candidate lines and rules that read the board. Computed once per game,
cached under data/study/<key>.json (a player's own game under data/study/mine/, never committed),
so a watched game answers at once the second time."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import chess
import chess.engine

from ..engine.pool import EnginePool, pool
from ..engine.score import cp_from_score, win_percent_from_cp
from ..openings.book import load_book
from ..review import classify as C
from ..review.report import _sacrificed_pawns
from ..settings import REPO_ROOT
from .reasons import forcing_gains, move_reasons, opponent_to_move, parried_threat

LOGGER = logging.getLogger("chess.study")
STUDY_DIR = REPO_ROOT / "data" / "study"
STUDY_DEPTH = 14
CANDIDATES = 3
THREAT_DEPTH = 10
LINE_PLIES = 6
THREAT_MIN_SWING = 10.0  # win% the opponent would gain with a free move: below this there is no threat worth naming
ONLY_MOVE_GAP = C.GREAT_SECOND_LINE_GAP
PROBLEM_CLASSES = (C.INACCURACY, C.MISTAKE, C.MISS, C.BLUNDER)


def study_key(start_fen: str, ucis: list[str]) -> str:
    return hashlib.sha1((start_fen + " " + " ".join(ucis)).encode()).hexdigest()[:16]


def _folder(mine: bool):
    return STUDY_DIR / "mine" if mine else STUDY_DIR


def cached(key: str, mine: bool = False) -> dict | None:
    path = _folder(mine) / f"{key}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _store(key: str, doc: dict, mine: bool = False) -> None:
    folder = _folder(mine)
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f"{key}.json.tmp"
    tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    tmp.replace(folder / f"{key}.json")


@dataclass
class Line:
    move: chess.Move
    cp_white: int
    pv: list[chess.Move]
    mate: int | None  # White's view: +N mates, -N gets mated

    @property
    def win_white(self) -> float:
        return win_percent_from_cp(self.cp_white)


async def _lines(board: chess.Board, engine: EnginePool, depth: int, multipv: int) -> list[Line]:
    if board.is_game_over():
        return []
    infos = await engine.analyse(board, depth=depth, multipv=multipv)
    out = []
    for info in infos:
        pv = info.get("pv") or []
        if not pv:
            continue
        score: chess.engine.PovScore = info["score"]
        out.append(Line(move=pv[0], cp_white=cp_from_score(score, chess.WHITE), pv=list(pv), mate=score.white().mate()))
    return out


def _sans(board: chess.Board, moves: list[chess.Move], n: int = LINE_PLIES) -> list[str]:
    b = board.copy(stack=False)
    out = []
    for mv in moves[:n]:
        if mv not in b.legal_moves:
            break
        out.append(b.san(mv))
        b.push(mv)
    return out


def _mover_win(win_white: float, mover: chess.Color) -> float:
    return win_white if mover == chess.WHITE else 100.0 - win_white


def _terminal_win(board: chess.Board, mover: chess.Color) -> float:
    """The mover's win% in a finished position: mate delivered is 100, any draw is 50."""
    if board.is_checkmate():
        return 100.0 if board.turn != mover else 0.0
    return 50.0


def _reply_story(before: chess.Board, move: chess.Move, reply: chess.Move | None, tail: list[chess.Move]) -> str:
    """What the engine's answer to a move does to the mover, in board words: the heart of "why not"."""
    after = before.copy(stack=False)
    after.push(move)
    if reply is None or reply not in after.legal_moves:
        return ""
    san = after.san(reply)
    reasons = move_reasons(after, reply)
    if reasons and reasons[0] == "checkmate":
        return f"{san} is checkmate"
    then = after.copy(stack=False)
    then.push(reply)
    if then.is_checkmate():
        return f"{san} mates"
    if reasons and reasons[0].startswith("gives up") and tail:  # a sacrifice means nothing without its follow-up
        return f"{san} {reasons[0]}, and then {' '.join(_sans(then, tail, 4))}"
    if reasons:
        return f"{san} {reasons[0]}"
    if tail:
        line = _sans(after, [reply, *tail], 5)
        return f"the engine answers {' '.join(line)}"
    return f"the engine answers {san}"


def parry_reason(before: chess.Board, move: chess.Move, parry: dict | None = None) -> str | None:
    """'parries the threat of Nxf7' or 'stops the mate threat Qxg7#' when the move takes a threat away."""
    parry = parry if parry is not None else parried_threat(before, move)
    if not parry:
        return None
    return f"stops the mate threat {parry['san']}" if parry["kind"] == "mate" else f"parries the threat of {parry['san']}"


def _gap_words(gap: float) -> str:
    if gap <= C.GOOD_MAX_DROP:
        return "just as good"
    if gap <= C.INACCURACY_MAX_DROP:
        return "a little worse"
    if gap <= C.MISTAKE_MAX_DROP:
        return "clearly worse"
    return "much worse"


def _why_not(before: chess.Board, cand: Line, cand_win: float, played_win: float, mover: chess.Color) -> str:
    gap = played_win - cand_win
    if gap <= C.GOOD_MAX_DROP:
        return "just as good"
    story = _reply_story(before, cand.move, cand.pv[1] if len(cand.pv) > 1 else None, cand.pv[2:])
    if cand.mate is not None and (cand.mate < 0) == (mover == chess.WHITE):
        return f"loses by force: {story or 'mate follows'}"
    return f"{_gap_words(gap)}: {story}" if story else _gap_words(gap)


def _spoken(reasons: list[str], classification: str, best_san: str | None, best_reason: str | None, problem: str | None, only_move: bool) -> str:
    """The narration for a move nobody annotated, from the facts only."""
    parts: list[str] = []
    if reasons:
        head = reasons[0] if len(reasons) == 1 or reasons[0] == "checkmate" else f"{reasons[0]} and {reasons[1]}"
        parts.append(head[0].upper() + head[1:] + ".")
    elif classification in (C.BEST, C.GREAT, C.BOOK):
        parts.append("The engine's first choice." if classification != C.BOOK else "A book move.")
    if only_move and classification not in PROBLEM_CLASSES:
        parts.append("The only move.")
    if classification in PROBLEM_CLASSES and best_san:
        label = {C.INACCURACY: "An inaccuracy", C.MISTAKE: "A mistake", C.MISS: "A missed chance", C.BLUNDER: "A blunder"}[classification]
        why = f": {problem}" if problem else ""
        parts.append(f"{label}{why}. Better was {best_san}" + (f", which {best_reason}." if best_reason else "."))
    return " ".join(parts)


async def annotate(moves: list[chess.Move], engine: EnginePool = pool, *, start_fen: str | None = None, depth: int = STUDY_DEPTH,
                   progress: Callable[[int, int], Awaitable[None]] | None = None) -> dict:
    """Every ply explained: the move's reasons, the engine's candidates with why-not stories, the threat it met."""
    board = chess.Board(start_fen) if start_fen else chess.Board()
    positions = [board.copy(stack=False)]
    for mv in moves:
        if mv not in board.legal_moves:
            raise ValueError(f"illegal move {mv.uci()} at ply {board.ply()} in {board.fen()!r}")
        board.push(mv)
        positions.append(board.copy(stack=False))
    total = len(positions)
    lines: list[list[Line]] = []
    for i, pos in enumerate(positions):
        lines.append(await _lines(pos, engine, depth, CANDIDATES))
        if progress:
            await progress(i + 1, total)
    book = load_book()
    plies: list[dict] = []
    prev_class: str | None = None
    for i, mv in enumerate(moves):
        before, after = positions[i], positions[i + 1]
        mover = before.turn
        cands = lines[i]
        best = cands[0] if cands else None
        win_before = _mover_win(best.win_white, mover) if best else 50.0
        nxt = lines[i + 1]
        win_after = _mover_win(nxt[0].win_white, mover) if nxt else _terminal_win(after, mover)
        rank = next((k for k, ln in enumerate(cands) if ln.move == mv), None)
        played_cp = (-cp_from_score_mover(nxt[0], after.turn) if nxt else None)
        best_cp = cp_from_score_mover(best, mover) if best else None
        cp_loss = max(0, best_cp - played_cp) if (best_cp is not None and played_cp is not None) else 0
        second = _mover_win(cands[1].win_white, mover) if len(cands) > 1 else None
        opening = book.lookup(after)
        mate_missed = best is not None and best.mate is not None and ((best.mate > 0) == (mover == chess.WHITE)) and not (nxt and nxt[0].mate is not None and ((nxt[0].mate > 0) == (mover == chess.WHITE)))
        classification = C.classify_move(
            win_before=win_before, win_after=win_after, second_best_win=second, is_best=rank == 0,
            is_book=opening is not None and after.ply() <= C.BOOK_MAX_PLY, is_forced=before.legal_moves.count() == 1,
            cp_loss=cp_loss, sacrificed_pawns=_sacrificed_pawns(before, mv), opponent_prev_class=prev_class,
            best_win_was_available=win_before, in_check_before=before.is_check(), is_promotion=mv.promotion is not None, mate_missed=mate_missed,
        )
        prev_class = classification
        reasons = move_reasons(before, mv)
        parry = parried_threat(before, mv)
        if parry:
            reasons.insert(0 if parry["kind"] == "mate" else min(1, len(reasons)), parry_reason(before, mv, parry))
        only_move = second is not None and win_before - second >= ONLY_MOVE_GAP and rank == 0
        problem = _reply_story(before, mv, nxt[0].move, nxt[0].pv[1:]) if (nxt and classification in PROBLEM_CLASSES) else None
        candidates = []
        for k, ln in enumerate(cands):
            cw = _mover_win(ln.win_white, mover)
            c_reasons = reasons if k == rank else move_reasons(before, ln.move)
            candidates.append({
                "san": before.san(ln.move), "uci": ln.move.uci(), "eval": describe_score_cp(ln), "win": round(cw, 1),
                "line": _sans(before, ln.pv), "played": k == rank, "reasons": c_reasons,
                "why_not": None if k == rank or cw > win_after + C.GOOD_MAX_DROP else _why_not(before, ln, cw, win_after, mover),
            })
        best_reason = candidates[0]["reasons"][0] if candidates and candidates[0]["reasons"] and rank != 0 else None
        plies.append({
            "ply": after.ply(), "san": before.san(mv), "uci": mv.uci(), "fen_before": before.fen(), "fen_after": after.fen(),
            "classification": classification, "eval_before": describe_score_cp(best) if best else "-", "eval_after": describe_score_cp(nxt[0]) if nxt else ("#" if after.is_checkmate() else "½"),
            "win_before": round(win_before, 1), "win_after": round(win_after, 1), "rank": None if rank is None else rank + 1,
            "reasons": reasons, "problem": problem, "only_move": only_move,
            "say": _spoken(reasons, classification, candidates[0]["san"] if candidates and rank != 0 else None, best_reason, problem, only_move),
            "candidates": candidates, "threat": None, "opening": opening.name if opening else None,
        })
    # the threat each move faced: what the opponent would do with a free move, when it matters
    for i, ply in enumerate(plies):
        before = positions[i]
        ply["threat"] = await _threat(before, engine, ply["win_before"])
    doc = {"depth": depth, "candidates": CANDIDATES, "start_fen": positions[0].fen(), "plies": plies}
    return doc


def cp_from_score_mover(line: Line, mover: chess.Color) -> int:
    return line.cp_white if mover == chess.WHITE else -line.cp_white


def describe_score_cp(line: Line) -> str:
    if line.mate is not None:
        return f"M{line.mate}" if line.mate > 0 else f"-M{-line.mate}"
    return f"{line.cp_white / 100:+.2f}"


async def _threat(before: chess.Board, engine: EnginePool, win_before: float) -> dict | None:
    """The opponent's best idea if the mover passed, when it would swing the game by THREAT_MIN_SWING or more."""
    if before.is_check() or before.is_game_over():
        return None
    b = opponent_to_move(before)
    if not b.is_valid():
        return None
    lines = await _lines(b, engine, THREAT_DEPTH, 1)
    if not lines:
        return None
    opp_win = _mover_win(lines[0].win_white, b.turn)
    swing = opp_win - (100.0 - win_before)
    if swing < THREAT_MIN_SWING:
        rules = forcing_gains(b)
        if not rules or rules[0]["gain"] < 3:
            return None
        return {"san": rules[0]["san"], "line": [rules[0]["san"]], "swing": round(swing, 1), "kind": rules[0]["kind"]}
    reasons = move_reasons(b, lines[0].move)
    return {"san": b.san(lines[0].move), "line": _sans(b, lines[0].pv, 5), "swing": round(swing, 1), "kind": "mate" if lines[0].mate is not None else "engine",
            "reason": reasons[0] if reasons else None}


# ---------------------------------------------------------------- jobs: compute once, poll meanwhile

@dataclass
class StudyJob:
    key: str
    done: int = 0
    total: int = 0
    error: str | None = None
    task: asyncio.Task | None = field(default=None, repr=False)


_jobs: dict[str, StudyJob] = {}


async def study_or_start(moves: list[chess.Move], start_fen: str | None = None, mine: bool = False) -> dict:
    """The cached study, or the job computing it: {"status": done|running|failed, "progress", "study"}.
    `mine` keeps a player's own game out of the committed content folder."""
    fen = start_fen or chess.STARTING_FEN
    key = study_key(fen, [m.uci() for m in moves])
    doc = cached(key, mine)
    if doc:
        return {"status": "done", "progress": {"done": len(doc["plies"]) + 1, "total": len(doc["plies"]) + 1}, "study": doc}
    job = _jobs.get(key)
    if job is None or (job.task and job.task.done() and job.error):
        job = StudyJob(key=key, total=len(moves) + 1)
        _jobs[key] = job
        job.task = asyncio.create_task(_run(job, moves, fen, mine))
    status = "failed" if job.error else "running"
    return {"status": status, "progress": {"done": job.done, "total": job.total}, "study": None, "error": job.error}


async def _run(job: StudyJob, moves: list[chess.Move], start_fen: str, mine: bool) -> None:
    async def progress(done: int, total: int) -> None:
        job.done, job.total = done, total

    try:
        doc = await annotate(moves, pool, start_fen=start_fen, progress=progress)
        _store(job.key, doc, mine)
        LOGGER.info("study done key=%s plies=%d depth=%d", job.key, len(moves), STUDY_DEPTH)
    except Exception as exc:  # boundary: the poller must learn the job failed
        job.error = f"{type(exc).__name__}: {exc}"
        LOGGER.error("study failed key=%s", job.key, exc_info=True)
    finally:
        if not job.error:
            _jobs.pop(job.key, None)
