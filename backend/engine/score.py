"""Score conversions shared by review, bots and the coach. Centipawns to win percentage uses
the lichess curve (lila: WinPercent.scala); mate scores clamp to the ends of that curve."""
from __future__ import annotations

import math

import chess
import chess.engine

MATE_CP = 10_000
_K = -0.00368208


def win_percent_from_cp(cp: int) -> float:
    """White-perspective win chance, 0..100."""
    cp = max(-MATE_CP, min(MATE_CP, cp))
    return 50.0 + 50.0 * (2.0 / (1.0 + math.exp(_K * cp)) - 1.0)


def cp_from_score(score: chess.engine.PovScore, pov: chess.Color = chess.WHITE) -> int:
    """Centipawns from the given side's view. Mate in N becomes ±(MATE_CP - N) so a faster mate
    scores higher than a slower one; a mate already on the board is +MATE_CP for the winner."""
    return score.pov(pov).score(mate_score=MATE_CP)


def win_percent_from_score(score: chess.engine.PovScore, pov: chess.Color = chess.WHITE) -> float:
    return win_percent_from_cp(cp_from_score(score, pov))


def move_accuracy(win_before: float, win_after: float) -> float:
    """lichess per-move accuracy from the mover's win% before and after the move."""
    drop = max(0.0, win_before - win_after)
    acc = 103.1668 * math.exp(-0.04354 * drop) - 3.1669
    return max(0.0, min(100.0, acc))


def describe_score(score: chess.engine.PovScore, pov: chess.Color = chess.WHITE) -> str:
    """'+1.3', '-0.4', 'M3', '-M2' from the given side's view."""
    s = score.pov(pov)
    if s.is_mate():
        n = s.mate() or 0
        if n == 0:
            return "#"
        return f"M{n}" if n > 0 else f"-M{abs(n)}"
    cp = s.score() or 0
    return f"{cp / 100:+.2f}"
