"""One home for a puzzle's rating: a measured rating (lichess, thousands of real solves) when the puzzle
carries one, else an estimate from its shape: a forcing first move is easier than a quiet one, a hanging
piece easier than a deflection. Used by the importer, the generator, mistake puzzles and recalibration."""
from __future__ import annotations

import chess

from ..coach.facts import PIECE_VALUES

BASE = 850
PER_EXTRA_MOVE = 150
MAX_LENGTH_BONUS = 450
MIN_RATING, MAX_RATING = 400, 2000
SUBTLE_THEMES = ("deflection", "attraction", "clearance", "interference", "zugzwang", "quietMove", "defensiveMove")
BASIC_THEMES = ("fork", "pin", "skewer", "backRankMate", "hangingPiece")


def _gives_up_material(board: chess.Board, move: chess.Move) -> bool:
    """The first move leaves the moved piece en prise for less than it took: a sacrifice to see through."""
    piece = board.piece_at(move.from_square)
    if piece is None or piece.piece_type == chess.KING:
        return False
    taken = board.piece_at(move.to_square)
    gained = PIECE_VALUES[taken.piece_type] if taken else 0
    after = board.copy(stack=False)
    after.push(move)
    attackers = after.attackers(after.turn, move.to_square)
    if not attackers:
        return False
    defended = after.attackers(not after.turn, move.to_square)
    cheapest = min(PIECE_VALUES[after.piece_at(a).piece_type] for a in attackers)
    loss = PIECE_VALUES[piece.piece_type] - (cheapest if defended else 0)
    return loss - gained >= 2


def difficulty(fen: str, moves: list[str], themes: list[str], *, solver_first: bool = False, measured: int | None = None) -> int:
    """The measured rating when there is one, else a rating from the puzzle's shape. `moves` is the
    lichess-shaped line (the opponent's move first unless solver_first)."""
    if measured is not None:
        return measured
    board = chess.Board(fen)
    line = [chess.Move.from_uci(m) for m in moves]
    if not solver_first and line:
        board.push(line[0])
        line = line[1:]
    if not line:
        return MIN_RATING
    first = line[0]
    n_solver = (len(line) + 1) // 2
    if "mateIn1" in themes:
        r = 600 + (150 if "quietMove" in themes else 0)
    else:
        r = BASE + min(MAX_LENGTH_BONUS, PER_EXTRA_MOVE * (n_solver - 1))
    forcing = board.is_capture(first) or board.gives_check(first)
    r += -50 if forcing else 200
    if _gives_up_material(board, first):
        r += 200
    if any(t in themes for t in SUBTLE_THEMES):
        r += 200
    if any(t in themes for t in BASIC_THEMES) and n_solver <= 2:
        r -= 50
    if "hangingPiece" in themes:
        r -= 100
    if "crushing" in themes or "mate" in themes:
        r -= 50
    if "endgame" in themes:
        r += 50
    if "blunder" in themes:  # a puzzle from the player's own game: the engine found the punishment obvious
        r -= 100
    return max(MIN_RATING, min(MAX_RATING, int(round(r, -1))))
