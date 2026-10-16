"""Game phase boundaries, after lichess's Divider: the opening ends when the position opens up
(few pieces on the back ranks, or enough material gone), the endgame begins when six or fewer
non-pawn pieces remain."""
from __future__ import annotations

import chess

OPENING = "opening"
MIDDLEGAME = "middlegame"
ENDGAME = "endgame"


def _non_pawn_pieces(board: chess.Board) -> int:
    return sum(len(board.pieces(pt, c)) for c in (chess.WHITE, chess.BLACK)
               for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN))


def _back_rank_pieces(board: chess.Board, color: chess.Color) -> int:
    rank = 0 if color == chess.WHITE else 7
    return sum(1 for f in range(8) if (p := board.piece_at(chess.square(f, rank))) and p.color == color and p.piece_type != chess.KING)


def phase_of(board: chess.Board, ply: int) -> str:
    pieces = _non_pawn_pieces(board)
    if pieces <= 6:
        return ENDGAME
    if pieces <= 10 or ply >= 30:
        return MIDDLEGAME
    if ply >= 12 and (_back_rank_pieces(board, chess.WHITE) <= 3 or _back_rank_pieces(board, chess.BLACK) <= 3):
        return MIDDLEGAME
    return OPENING


def phases_for_game(boards: list[chess.Board]) -> list[str]:
    """One phase per position, monotone: once the middlegame starts the opening never returns."""
    out: list[str] = []
    reached = OPENING
    order = {OPENING: 0, MIDDLEGAME: 1, ENDGAME: 2}
    for ply, b in enumerate(boards):
        p = phase_of(b, ply)
        if order[p] > order[reached]:
            reached = p
        out.append(reached)
    return out
