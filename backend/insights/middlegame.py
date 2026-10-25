"""Middlegame findings: the imbalances you reach at move 20 and how you score from them, how active
your pieces are against the opponent's, and whether your mistakes miss tactics or plans."""
from __future__ import annotations

from collections import defaultdict

import chess

from ..coach.facts import _side_facts
from ..review.phases import ENDGAME, MIDDLEGAME
from ..study.assess import imbalances
from . import resources
from .games import ERRORS, Game, example, mean, record

SAMPLE_PLY = 40  # move 20: the structure is set and the endgame has usually not begun
MIN_GAMES = 3
# The master-game theme that shows an imbalance played well.
_WATCH = {"isolated pawn": "iqp", "bishop pair": "bishop-pair", "doubled pawns": "pawn-structure", "passed pawn": "endgame",
          "king attack": "attack", "weak king cover": "attack", "king in the centre": "development", "space": "positional",
          "activity": "initiative", "outpost": "positional", "open file": "positional", "material": "defence", "development": "development"}


def sample_index(game: Game) -> int | None:
    """The position the findings read: move 20 while the middlegame lasts, else its last position."""
    mg = game.boundaries.get(MIDDLEGAME)
    if mg is None:
        return None
    i = max(mg, min(SAMPLE_PLY, len(game.positions) - 1))
    eg = game.boundaries.get(ENDGAME)
    if eg is not None:
        i = min(i, eg - 1)
    return i if i >= mg else None


def middlegame(games: list[Game], level: dict | None) -> dict:
    band, rating = resources.band_of(level), resources.rating_of(level)
    by_kind: dict[tuple[str, bool], list[Game]] = defaultdict(list)
    samples: dict[str, tuple[int, str]] = {}
    mobility: list[int] = []
    for g in games:
        i = sample_index(g)
        if i is None:
            continue
        board = chess.Board(g.positions[i])
        samples[g.id] = (i, g.positions[i])
        me = chess.WHITE if g.color == "white" else chess.BLACK
        mobility.append(_side_facts(board, me).mobility - _side_facts(board, not me).mobility)
        for item in imbalances(board):
            if item["side"] != "both":
                by_kind[(item["kind"], item["side"].lower() == g.color)].append(g)
    rows = []
    for (kind, mine), gs in by_kind.items():
        if len(gs) < MIN_GAMES:
            continue
        shown = min(gs, key=lambda g: g.score) if mine else max(gs, key=lambda g: g.score)
        rows.append({"kind": kind, "mine": mine, **record(gs), "example": {"game_id": shown.id, "ply": samples[shown.id][0], "fen": samples[shown.id][1], "outcome": shown.outcome, "opponent": shown.opponent},
                     "watch": resources.master_game(_WATCH.get(kind, "positional"), band)})
    rows.sort(key=lambda r: -r["score"])
    errors = {"tactic": [], "plan": []}
    for g in games:
        for m in g.moves:
            if m.phase == MIDDLEGAME and m.classification in ERRORS:
                errors["tactic" if m.motif else "plan"].append((g, m))
    n = max(1, len(games))
    kinds = {k: {"count": len(v), "drop_per_game": round(sum(m.drop for _, m in v) / n, 1), "example": example(*max(v, key=lambda gm: gm[1].drop)) if v else None} for k, v in errors.items()}
    total = kinds["tactic"]["count"] + kinds["plan"]["count"]
    finding = None
    if total:
        tactic = kinds["tactic"]["count"]
        finding = f"Of your {total} middlegame mistakes, {tactic} missed a tactic the engine's move makes and {total - tactic} were quiet moves where the plan was wrong."
    worst = min((r for r in rows if r["mine"]), key=lambda r: r["score"], default=None)
    if worst and worst["score"] is not None and worst["score"] < 50:
        finding = (finding + " " if finding else "") + f"With {worst['kind']} on your side you score {worst['score']}% over {worst['games']} games."
    plan_heavy = kinds["plan"]["count"] >= kinds["tactic"]["count"]
    action = resources.lesson_in("middlegame", band) if plan_heavy else resources.lesson_in("thinking", band)
    return {"games": len(samples), "needs": max(0, MIN_GAMES - len(samples)), "imbalances": rows,
            "mobility": {"games": len(mobility), "mean_diff": mean(mobility)} if len(mobility) >= MIN_GAMES else None,
            "errors": kinds, "finding": finding, "action": action, "watch": worst["watch"] if worst else None,
            "bot": resources.bot(MIDDLEGAME, "attack" if _WATCH.get(worst["kind"]) == "attack" else "positional", rating) if worst else None}
