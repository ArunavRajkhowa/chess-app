"""Move classification and accuracy, the heart of Game Review. Every threshold lives here.
Win percentages are the mover's, 0..100, from the lichess centipawn curve (engine/score.py)."""
from __future__ import annotations

import math
from dataclasses import dataclass

# Classification names are wire values: the frontend maps them to icons and colours.
BRILLIANT = "brilliant"
GREAT = "great"
BEST = "best"
EXCELLENT = "excellent"
GOOD = "good"
BOOK = "book"
INACCURACY = "inaccuracy"
MISTAKE = "mistake"
MISS = "miss"
BLUNDER = "blunder"
FORCED = "forced"

ALL_CLASSES = (BRILLIANT, GREAT, BEST, EXCELLENT, GOOD, BOOK, INACCURACY, MISTAKE, MISS, BLUNDER, FORCED)

# Win% drop thresholds (mover's view). A drop below EXCELLENT_MAX_DROP that is not the engine's
# top move is "excellent"; the top move is "best" whatever its drop.
EXCELLENT_MAX_DROP = 2.0
GOOD_MAX_DROP = 5.0
INACCURACY_MAX_DROP = 10.0
MISTAKE_MAX_DROP = 20.0

# "Great": the engine's top move while the second-best line is this much worse, or the top move
# right after the opponent's mistake/blunder (a punish).
GREAT_SECOND_LINE_GAP = 10.0
# "Brilliant": a sound sacrifice. The move must be (near) best, give up material, not start from a
# lost position, and not be a trivially winning position already.
BRILLIANT_MAX_DROP = 2.0
BRILLIANT_MIN_WIN_AFTER = 40.0
BRILLIANT_MAX_WIN_BEFORE = 92.0
BRILLIANT_MIN_SACRIFICE_PAWNS = 2  # knight or more, or two pawns of material given up
BRILLIANT_WINNING_ANYWAY_SECOND_WIN = 95.0  # second-best line already this good: no brilliancy
# "Miss": the mover had a winning shot (best line this good) and played something clearly worse.
MISS_MIN_BEST_WIN = 85.0
MISS_MIN_DROP = 10.0

# Opening book moves count as book only this far into the game.
BOOK_MAX_PLY = 24


@dataclass(frozen=True)
class MoveJudgement:
    classification: str
    accuracy: float
    win_before: float
    win_after: float
    cp_loss: int


def classify_move(
    *,
    win_before: float,
    win_after: float,
    second_best_win: float | None,
    is_best: bool,
    is_book: bool,
    is_forced: bool,
    cp_loss: int,
    sacrificed_pawns: int,
    opponent_prev_class: str | None,
    best_win_was_available: float,
    in_check_before: bool = False,
    is_promotion: bool = False,
) -> str:
    """Decide one move's label. `best_win_was_available` is the mover's win% if they had played the
    engine's top move (equal to win_before by construction, kept explicit for the Miss rule)."""
    if is_forced:
        return FORCED
    if is_book:
        return BOOK
    drop = max(0.0, win_before - win_after)

    if is_best or cp_loss <= 0:
        winning_anyway = second_best_win is not None and second_best_win >= BRILLIANT_WINNING_ANYWAY_SECOND_WIN
        if (
            sacrificed_pawns >= BRILLIANT_MIN_SACRIFICE_PAWNS
            and drop <= BRILLIANT_MAX_DROP
            and win_after >= BRILLIANT_MIN_WIN_AFTER
            and win_before <= BRILLIANT_MAX_WIN_BEFORE
            and not in_check_before
            and not is_promotion
            and not winning_anyway
        ):
            return BRILLIANT
        punish = opponent_prev_class in (MISTAKE, BLUNDER, MISS)
        only_move = second_best_win is not None and (win_before - second_best_win) >= GREAT_SECOND_LINE_GAP
        if (only_move or punish) and win_before >= 45.0:
            return GREAT
        return BEST

    if best_win_was_available >= MISS_MIN_BEST_WIN and drop >= MISS_MIN_DROP and win_after < MISS_MIN_BEST_WIN:
        return MISS
    if drop <= EXCELLENT_MAX_DROP:
        return EXCELLENT
    if drop <= GOOD_MAX_DROP:
        return GOOD
    if drop <= INACCURACY_MAX_DROP:
        return INACCURACY
    if drop <= MISTAKE_MAX_DROP:
        return MISTAKE
    return BLUNDER


def move_accuracy(win_before: float, win_after: float) -> float:
    drop = max(0.0, win_before - win_after)
    return max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * drop) - 3.1669))


def game_accuracy(win_percents_white_view: list[float], move_accuracies: list[float]) -> float:
    """lichess game accuracy: the mean of a volatility-weighted average and the harmonic mean of
    the per-move accuracies. `win_percents_white_view` has one entry per position (n+1)."""
    if not move_accuracies:
        return 100.0
    n = len(win_percents_white_view)
    window = max(2, min(8, n // 10))
    windows: list[list[float]] = []
    for i in range(len(move_accuracies)):
        lo = max(0, i + 1 - window)
        windows.append(win_percents_white_view[lo : i + 2])
    weights = []
    for w in windows:
        mean = sum(w) / len(w)
        var = sum((x - mean) ** 2 for x in w) / len(w)
        weights.append(max(0.5, min(12.0, math.sqrt(var))))
    weighted = sum(a * w for a, w in zip(move_accuracies, weights)) / sum(weights)
    harmonic = len(move_accuracies) / sum(1.0 / max(a, 0.01) for a in move_accuracies)
    return round((weighted + harmonic) / 2.0, 1)


_ACPL_TO_ELO = [(5, 2800), (10, 2600), (15, 2400), (20, 2250), (25, 2100), (30, 2000), (40, 1800),
                (50, 1600), (60, 1450), (70, 1300), (85, 1150), (100, 1000), (130, 800), (170, 600), (250, 400)]


def estimate_rating(acpl: float) -> int:
    """A rough performance estimate from average centipawn loss; a table, not a model."""
    if acpl <= _ACPL_TO_ELO[0][0]:
        return _ACPL_TO_ELO[0][1]
    for (a0, e0), (a1, e1) in zip(_ACPL_TO_ELO, _ACPL_TO_ELO[1:]):
        if acpl <= a1:
            t = (acpl - a0) / (a1 - a0)
            return int(round(e0 + (e1 - e0) * t, -1))
    return 300
