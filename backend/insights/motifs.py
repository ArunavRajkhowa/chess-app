"""The tactical motif of a move, named as a puzzle theme, from what reasons.py says the move does.
A move the rules cannot name has no motif: a quiet move, a plan, not a tactic."""
from __future__ import annotations

import chess

from ..study.reasons import move_reasons

# A reason's opening words and the puzzle theme they name; first match wins, in reasons.py's order.
_REASON_THEMES = (
    ("checkmate", "mate"),
    ("takes the", "hangingPiece"),  # "... for free"
    ("wins the", "hangingPiece"),  # a capture that wins material: the target is not held
    ("forks the", "fork"),
    ("pins the", "pin"),
    ("uncovers an attack", "discoveredAttack"),
    ("promotes to", "promotion"),
)
TACTICAL = frozenset(theme for _, theme in _REASON_THEMES)


_CAPTURE_HEADS = ("takes the", "wins the")


def motif_of(board: chess.Board, move: chess.Move, recapture_square: int | None = None) -> str | None:
    """The theme of the move; a capture on `recapture_square` (where the opponent just captured) is a trade, not a tactic."""
    for reason in move_reasons(board, move):
        for head, theme in _REASON_THEMES:
            if head in _CAPTURE_HEADS and move.to_square == recapture_square:
                continue
            if reason.startswith(head) and (head != "takes the" or reason.endswith("for free")):
                return theme
    return None
