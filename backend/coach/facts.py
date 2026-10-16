"""The position fact sheet: everything the coach may say about a position, computed by rules
and the engine so the model explains facts instead of inventing them. Every move the coach is
allowed to name is in `candidate_moves` or `threats`."""
from __future__ import annotations

from dataclasses import dataclass, field

import chess
import chess.engine

from ..engine.pool import EnginePool
from ..engine.score import cp_from_score, describe_score, win_percent_from_cp
from ..openings.book import load_book
from ..review.phases import phase_of

PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
NAMES = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop", chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king"}


@dataclass
class SideFacts:
    material: int
    pieces: dict[str, int]
    king_square: str
    castled: str  # "kingside" | "queenside" | "not yet" | "cannot"
    king_shield_pawns: int
    attackers_near_king: int
    developed_minors: int
    isolated_pawns: list[str]
    doubled_files: list[str]
    passed_pawns: list[str]
    backward_pawns: list[str] = field(default_factory=list)
    hanging_pieces: list[str] = field(default_factory=list)
    pinned_pieces: list[str] = field(default_factory=list)
    mobility: int = 0
    open_files_for_rooks: list[str] = field(default_factory=list)


def _pawn_files(board: chess.Board, color: chess.Color) -> dict[int, list[int]]:
    files: dict[int, list[int]] = {}
    for sq in board.pieces(chess.PAWN, color):
        files.setdefault(chess.square_file(sq), []).append(chess.square_rank(sq))
    return files


def _passed(board: chess.Board, sq: int, color: chess.Color) -> bool:
    f, r = chess.square_file(sq), chess.square_rank(sq)
    ahead = range(r + 1, 8) if color == chess.WHITE else range(0, r)
    for df in (-1, 0, 1):
        ff = f + df
        if 0 <= ff < 8:
            for rr in ahead:
                p = board.piece_at(chess.square(ff, rr))
                if p and p.piece_type == chess.PAWN and p.color != color:
                    return False
    return True


def _side_facts(board: chess.Board, color: chess.Color) -> SideFacts:
    pieces = {NAMES[pt]: len(board.pieces(pt, color)) for pt in PIECE_VALUES}
    material = sum(PIECE_VALUES[pt] * len(board.pieces(pt, color)) for pt in PIECE_VALUES)
    ksq = board.king(color)
    king_square = chess.square_name(ksq) if ksq is not None else "-"
    home_rank = 0 if color == chess.WHITE else 7
    castled = "not yet"
    if ksq is not None:
        kf = chess.square_file(ksq)
        if chess.square_rank(ksq) == home_rank and kf >= 6:
            castled = "kingside"
        elif chess.square_rank(ksq) == home_rank and kf <= 2:
            castled = "queenside"
        elif not board.has_castling_rights(color):
            castled = "cannot"
    shield = 0
    attackers = 0
    if ksq is not None:
        for df in (-1, 0, 1):
            ff = chess.square_file(ksq) + df
            rr = chess.square_rank(ksq) + (1 if color == chess.WHITE else -1)
            if 0 <= ff < 8 and 0 <= rr < 8:
                p = board.piece_at(chess.square(ff, rr))
                if p and p.piece_type == chess.PAWN and p.color == color:
                    shield += 1
        zone = [s for s in chess.SQUARES if chess.square_distance(s, ksq) <= 2]
        attackers = len({a for s in zone for a in board.attackers(not color, s) if board.piece_at(a) and board.piece_at(a).piece_type != chess.PAWN})
    developed = 0
    for pt in (chess.KNIGHT, chess.BISHOP):
        for sq in board.pieces(pt, color):
            if chess.square_rank(sq) != home_rank:
                developed += 1
    files = _pawn_files(board, color)
    isolated = [chess.square_name(chess.square(f, r)) for f, ranks in files.items() for r in ranks if (f - 1) not in files and (f + 1) not in files]
    doubled = [chess.FILE_NAMES[f] for f, ranks in files.items() if len(ranks) > 1]
    passed = [chess.square_name(sq) for sq in board.pieces(chess.PAWN, color) if _passed(board, sq, color)]
    hanging: list[str] = []
    pinned: list[str] = []
    for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        for sq in board.pieces(pt, color):
            atk = board.attackers(not color, sq)
            if atk:
                defended = board.attackers(color, sq)
                cheapest = min(PIECE_VALUES[board.piece_at(a).piece_type] for a in atk)
                if not defended or cheapest < PIECE_VALUES[pt]:
                    hanging.append(f"{NAMES[pt]} on {chess.square_name(sq)}")
            if board.is_pinned(color, sq):
                pinned.append(f"{NAMES[pt]} on {chess.square_name(sq)}")
    mobility = 0
    if board.turn == color:
        mobility = board.legal_moves.count()
    else:
        b = board.copy()
        b.turn = color
        if not b.is_check():
            mobility = b.legal_moves.count()
    all_files = _pawn_files(board, chess.WHITE), _pawn_files(board, chess.BLACK)
    open_files = [chess.FILE_NAMES[f] for f in range(8) if f not in all_files[0] and f not in all_files[1]]
    return SideFacts(
        material=material, pieces=pieces, king_square=king_square, castled=castled, king_shield_pawns=shield,
        attackers_near_king=attackers, developed_minors=developed, isolated_pawns=isolated, doubled_files=doubled,
        passed_pawns=passed, hanging_pieces=hanging, pinned_pieces=pinned, mobility=mobility, open_files_for_rooks=open_files,
    )


def _line_san(board: chess.Board, pv: list[chess.Move], n: int = 6) -> list[str]:
    b = board.copy()
    out = []
    for mv in pv[:n]:
        out.append(b.san(mv))
        b.push(mv)
    return out


async def position_facts(board: chess.Board, pool: EnginePool, *, depth: int = 14, multipv: int = 3,
                         last_move: chess.Move | None = None) -> dict:
    infos = [] if board.is_game_over() else await pool.analyse(board, depth=depth, multipv=multipv)
    candidates = []
    for info in infos:
        pv = info.get("pv") or []
        if not pv:
            continue
        candidates.append({
            "move": board.san(pv[0]), "uci": pv[0].uci(), "eval": describe_score(info["score"], chess.WHITE),
            "win_percent_white": round(win_percent_from_cp(cp_from_score(info["score"], chess.WHITE)), 1),
            "line": _line_san(board, pv),
        })
    white = _side_facts(board, chess.WHITE)
    black = _side_facts(board, chess.BLACK)
    opening = load_book().lookup(board)
    from ..routers.play import threat_moves  # rule-based threats, shared with the play API

    threats = threat_moves(board)
    return {
        "fen": board.fen(),
        "side_to_move": "white" if board.turn == chess.WHITE else "black",
        "move_number": board.fullmove_number,
        "phase": phase_of(board, board.ply()),
        "in_check": board.is_check(),
        "game_over": board.is_game_over(),
        "last_move": None if last_move is None else _describe_last_move(board, last_move),
        "opening": {"eco": opening.eco, "name": opening.name} if opening else None,
        "evaluation": candidates[0]["eval"] if candidates else ("#" if board.is_checkmate() else "½"),
        "material_balance_white": white.material - black.material,
        "white": white.__dict__,
        "black": black.__dict__,
        "candidate_moves": candidates,
        "threats_against_side_to_move": threats,
    }


def _describe_last_move(board: chess.Board, move: chess.Move) -> dict:
    b = board.copy()
    try:
        b.pop()
    except IndexError:
        return {"uci": move.uci()}
    san = b.san(move)
    piece = b.piece_at(move.from_square)
    captured = b.piece_at(move.to_square)
    return {
        "san": san, "uci": move.uci(), "piece": NAMES[piece.piece_type] if piece else None,
        "captured": NAMES[captured.piece_type] if captured else None, "gives_check": board.is_check(),
        "is_castling": b.is_castling(move),
    }
