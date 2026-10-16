"""Game Review: analyses every position once, judges every move, and builds the report the
frontend renders. Depth is the cost lever: 12 is a quick look, 18 a serious review."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field

import chess
import chess.engine

from ..engine.pool import EnginePool
from ..engine.score import MATE_CP, cp_from_score, describe_score, win_percent_from_cp
from ..openings.book import load_book
from . import classify as C
from .phases import ENDGAME, MIDDLEGAME, OPENING, phases_for_game

LOGGER = logging.getLogger("chess.review")

PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
KEY_MOMENT_MIN_SWING = 12.0


@dataclass
class ReviewedMove:
    ply: int
    move_number: int
    color: str
    san: str
    uci: str
    fen_before: str
    fen_after: str
    classification: str
    accuracy: float
    win_before: float
    win_after: float
    cp_loss: int
    eval_after_cp: int
    eval_after_text: str
    best_move_san: str
    best_move_uci: str
    best_line_san: list[str]
    best_eval_text: str
    phase: str
    is_key_moment: bool = False
    note: str = ""


@dataclass
class SideSummary:
    accuracy: float
    acpl: float
    estimated_rating: int
    counts: dict[str, int]
    phase_accuracy: dict[str, float | None]


@dataclass
class GameReport:
    moves: list[ReviewedMove]
    white: SideSummary
    black: SideSummary
    opening: dict | None
    depth: int
    result: str | None
    eval_graph: list[float]  # white win% per position, len = plies + 1
    key_moments: list[int] = field(default_factory=list)  # plies
    phase_boundaries: dict[str, int | None] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _sacrificed_pawns(board: chess.Board, move: chess.Move) -> int:
    """Material the mover offers with this move: the moved piece's value if it lands on a square the
    opponent can take without losing more (static exchange), minus any capture it makes."""
    mover = board.piece_at(move.from_square)
    if mover is None or mover.piece_type == chess.KING:
        return 0
    gained = PIECE_VALUES[board.piece_at(move.to_square).piece_type] if board.is_capture(move) and board.piece_at(move.to_square) else (1 if board.is_en_passant(move) else 0)
    b = board.copy()
    b.push(move)
    attackers = b.attackers(b.turn, move.to_square)
    if not attackers:
        return 0
    cheapest = min(PIECE_VALUES[b.piece_at(sq).piece_type] for sq in attackers)
    defenders = b.attackers(not b.turn, move.to_square)
    landed = PIECE_VALUES[mover.piece_type if move.promotion is None else move.promotion]
    if defenders and cheapest >= landed:
        return 0
    loss = landed - (cheapest if defenders else 0)
    return max(0, loss - gained)


def _note_for(cls: str, rm_best_san: str, cp_loss: int, mover_mate_missed: bool) -> str:
    if cls == C.BRILLIANT:
        return "A sound sacrifice: the engine agrees and the material comes back with interest."
    if cls == C.GREAT:
        return "The only move that keeps the balance, or the move that punishes the mistake."
    if cls == C.BEST:
        return "The engine's first choice."
    if cls == C.EXCELLENT:
        return "Nearly as good as the best move."
    if cls == C.GOOD:
        return "A reasonable move; the best was a little better."
    if cls == C.BOOK:
        return "Opening theory."
    if cls == C.FORCED:
        return "The only legal move."
    if cls == C.MISS:
        return "A winning chance slipped away" + (f": {rm_best_san} was available." if rm_best_san else ".")
    if cls == C.INACCURACY:
        return f"Slightly imprecise. {rm_best_san} keeps more."
    if cls == C.MISTAKE:
        return f"This gives something away. {rm_best_san} was much better."
    if cls == C.BLUNDER:
        return ("This throws away a mate." if mover_mate_missed else f"A serious error. {rm_best_san} was the move.") + f" ({cp_loss / 100:.1f} pawns lost)"
    return ""


async def review_moves(
    moves: list[chess.Move],
    pool: EnginePool,
    *,
    depth: int = 16,
    multipv: int = 2,
    result: str | None = None,
    progress: Callable[[int, int], Awaitable[None]] | None = None,
    start_fen: str | None = None,
) -> GameReport:
    boards: list[chess.Board] = [chess.Board(start_fen) if start_fen else chess.Board()]
    for mv in moves:
        b = boards[-1].copy()
        b.push(mv)
        boards.append(b)
    n = len(moves)

    infos: list[list[chess.engine.InfoDict]] = []
    for i, b in enumerate(boards):
        if b.is_game_over():
            infos.append([])
        else:
            infos.append(await pool.analyse(b, depth=depth, multipv=multipv))
        if progress:
            await progress(i + 1, n + 1)

    book = load_book()
    opening, book_exit_ply = book.classify_game(moves) if not start_fen else (None, 0)
    phases = phases_for_game(boards)

    def side_cp(i: int, pov: chess.Color, line: int = 0) -> int | None:
        if not infos[i] or len(infos[i]) <= line:
            b = boards[i]
            if b.is_checkmate():
                return -MATE_CP if b.turn == pov else MATE_CP
            if b.is_game_over():
                return 0
            return None
        return cp_from_score(infos[i][line]["score"], pov)

    reviewed: list[ReviewedMove] = []
    prev_class: dict[chess.Color, str | None] = {chess.WHITE: None, chess.BLACK: None}
    white_graph: list[float] = []
    for i in range(n + 1):
        cp = side_cp(i, chess.WHITE)
        white_graph.append(win_percent_from_cp(cp if cp is not None else 0))

    for i, mv in enumerate(moves):
        board = boards[i]
        mover = board.turn
        before_cp = side_cp(i, mover) or 0
        after_cp = side_cp(i + 1, mover)
        if after_cp is None:
            after_cp = before_cp
        second_cp = side_cp(i, mover, 1) if len(infos[i]) > 1 else None
        win_before = win_percent_from_cp(before_cp)
        win_after = win_percent_from_cp(after_cp)
        second_win = win_percent_from_cp(second_cp) if second_cp is not None else None
        best_line = infos[i][0]["pv"] if infos[i] else []
        best_move = best_line[0] if best_line else mv
        is_best = best_move == mv
        cp_loss = max(0, before_cp - after_cp) if not is_best else 0
        in_book = (i + 1) <= book_exit_ply and (i + 1) <= C.BOOK_MAX_PLY
        forced = board.legal_moves.count() == 1
        sacrificed = _sacrificed_pawns(board, mv)
        cls = C.classify_move(
            win_before=win_before, win_after=win_after, second_best_win=second_win, is_best=is_best,
            is_book=in_book, is_forced=forced, cp_loss=cp_loss, sacrificed_pawns=sacrificed,
            opponent_prev_class=prev_class[not mover], best_win_was_available=win_before,
            in_check_before=board.is_check(), is_promotion=mv.promotion is not None,
        )
        prev_class[mover] = cls
        acc = C.move_accuracy(win_before, win_after)
        b2 = board.copy()
        line_san = []
        for lm in best_line[:6]:
            line_san.append(b2.san(lm))
            b2.push(lm)
        after_score_text = describe_score(infos[i + 1][0]["score"], chess.WHITE) if infos[i + 1] else ("#" if boards[i + 1].is_checkmate() else "½")
        mate_missed = before_cp >= MATE_CP - 50 and after_cp < MATE_CP - 50
        reviewed.append(ReviewedMove(
            ply=i + 1, move_number=i // 2 + 1, color="white" if mover == chess.WHITE else "black",
            san=board.san(mv), uci=mv.uci(), fen_before=board.fen(), fen_after=boards[i + 1].fen(),
            classification=cls, accuracy=round(acc, 1), win_before=round(win_before, 1), win_after=round(win_after, 1),
            cp_loss=cp_loss, eval_after_cp=side_cp(i + 1, chess.WHITE) or 0, eval_after_text=after_score_text,
            best_move_san=board.san(best_move), best_move_uci=best_move.uci(), best_line_san=line_san,
            best_eval_text=describe_score(infos[i][0]["score"], chess.WHITE) if infos[i] else "",
            phase=phases[i], note=_note_for(cls, board.san(best_move), cp_loss, mate_missed),
        ))

    key: list[int] = []
    for rm in reviewed:
        swing = abs(rm.win_before - rm.win_after)
        if rm.classification in (C.BRILLIANT, C.GREAT, C.BLUNDER, C.MISS) or (rm.classification == C.MISTAKE and swing >= KEY_MOMENT_MIN_SWING):
            rm.is_key_moment = True
            key.append(rm.ply)

    def summary(color: str) -> SideSummary:
        mine = [m for m in reviewed if m.color == color]
        if not mine:
            return SideSummary(accuracy=100.0, acpl=0.0, estimated_rating=0, counts={c: 0 for c in C.ALL_CLASSES}, phase_accuracy={})
        accs = [m.accuracy for m in mine]
        graph = white_graph if color == "white" else [100 - w for w in white_graph]
        acc = C.game_accuracy(graph, accs)
        acpl = sum(min(m.cp_loss, 1000) for m in mine) / len(mine)
        counts = {c: sum(1 for m in mine if m.classification == c) for c in C.ALL_CLASSES}
        phase_acc: dict[str, float | None] = {}
        for ph in (OPENING, MIDDLEGAME, ENDGAME):
            xs = [m.accuracy for m in mine if m.phase == ph]
            phase_acc[ph] = round(sum(xs) / len(xs), 1) if xs else None
        return SideSummary(accuracy=acc, acpl=round(acpl, 1), estimated_rating=C.estimate_rating(acpl), counts=counts, phase_accuracy=phase_acc)

    boundaries = {MIDDLEGAME: next((i for i, p in enumerate(phases) if p == MIDDLEGAME), None),
                  ENDGAME: next((i for i, p in enumerate(phases) if p == ENDGAME), None)}
    return GameReport(
        moves=reviewed, white=summary("white"), black=summary("black"),
        opening={"eco": opening.eco, "name": opening.name, "last_book_ply": book_exit_ply} if opening else None,
        depth=depth, result=result, eval_graph=[round(w, 1) for w in white_graph], key_moments=key,
        phase_boundaries=boundaries,
    )
