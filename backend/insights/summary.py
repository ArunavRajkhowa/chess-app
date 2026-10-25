"""The headline numbers (accuracy, accuracy per phase, move quality): the response fields the
coach reads, computed from the same loaded games."""
from __future__ import annotations

from collections import Counter, defaultdict

from ..review import classify as C
from .games import Game, mean


def summary(games: list[Game]) -> dict:
    accuracies = [g.accuracy for g in games if g.accuracy is not None]
    acc_by_phase: dict[str, list[float]] = defaultdict(list)
    counts: Counter = Counter()
    for g in games:
        for ph, v in g.phase_accuracy.items():
            if v is not None:
                acc_by_phase[ph].append(v)
        counts.update(g.counts)
    n = len(games)
    total_moves = sum(counts.values()) or 1
    return {
        "games": n,
        "accuracy": {"mean": mean(accuracies), "best": max(accuracies), "worst": min(accuracies),
                     "timeline": [{"at": g.created_at, "accuracy": g.accuracy, "game_id": g.id} for g in games if g.accuracy is not None]} if accuracies else None,
        "phase_accuracy": {k: round(sum(v) / len(v), 1) for k, v in acc_by_phase.items()},
        "move_quality": {k: {"count": counts[k], "per_game": round(counts[k] / n, 2), "share": round(100 * counts[k] / total_moves, 1)} for k in C.ALL_CLASSES},
    }
