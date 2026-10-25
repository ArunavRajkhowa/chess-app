"""Tactics findings: every position where the engine's move was a named motif, whether you found
it or missed it, and the motif you miss most, mapped to its puzzle theme and lesson."""
from __future__ import annotations

from collections import defaultdict

from ..puzzles.store import THEME_INFO
from . import resources
from .games import PROBLEM, Game, Move, example

MIN_MISSED = 2
MIN_SEEN_FOR_STRENGTH = 5
FOUND_RATE_STRENGTH = 0.8


def tactics(games: list[Game], level: dict | None) -> dict:
    rating, band = resources.rating_of(level), resources.band_of(level)
    puzzle_rating = rating if level and level["source"] == "puzzle rating" else None  # a review estimate is no puzzle rating
    hits: dict[str, dict] = defaultdict(lambda: {"found": 0, "missed": 0, "drop_total": 0.0, "worst": None})
    for g in games:
        for m in g.moves:
            if not m.motif:
                continue
            row = hits[m.motif]
            if m.uci == m.best_uci:
                row["found"] += 1
            elif m.classification in PROBLEM:
                row["missed"] += 1
                row["drop_total"] += m.drop
                if row["worst"] is None or m.drop > row["worst"][1].drop:
                    row["worst"] = (g, m)
    n = max(1, len(games))
    motifs = []
    for theme, row in hits.items():
        worst: tuple[Game, Move] | None = row["worst"]
        motifs.append({"theme": theme, "name": THEME_INFO[theme][0], "found": row["found"], "missed": row["missed"], "seen": row["found"] + row["missed"],
                       "drop_per_game": round(row["drop_total"] / n, 1), "example": example(*worst) if worst else None})
    motifs.sort(key=lambda r: (-r["missed"], -r["drop_per_game"]))
    most = next((r for r in motifs if r["missed"] >= MIN_MISSED), None)
    finding = f"You miss {most['name'].lower()}s most: {most['missed']} of {most['seen']} chances in your games." if most else None
    theme = most["theme"] if most else None
    return {
        "motifs": motifs, "most_missed": theme, "finding": finding,
        "action": (resources.puzzles(theme, puzzle_rating) if theme else None) or resources.lesson_in("tactics", band),
        "lesson": resources.lesson_for(theme) if theme else None, "bot": resources.bot("tactics", None, rating),
        "needs": 0 if most else MIN_MISSED - max((r["missed"] for r in motifs), default=0),
    }
