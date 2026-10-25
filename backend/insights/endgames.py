"""Endgame findings: the endgame types you reach, how often you convert a winning one and hold a
worse one, the type you lose most, and the drill and lesson for it."""
from __future__ import annotations

from collections import defaultdict

from ..review.phases import ENDGAME
from . import resources
from .games import ERRORS, Game, Move, example, mean, record

WINNING_WIN = 80.0  # win chance at the endgame's first position that counts as "winning"
MIN_GAMES = 2
TYPE_NAMES = {"pawn": "pawn endgame", "rook": "rook endgame", "minor": "minor-piece endgame", "queen": "queen endgame"}


def endgame_type(fen: str) -> str:
    """By the heaviest piece left: queen, rook, minor, else kings and pawns."""
    pieces = fen.split(" ")[0].lower()
    if "q" in pieces:
        return "queen"
    if "r" in pieces:
        return "rook"
    if "n" in pieces or "b" in pieces:
        return "minor"
    return "pawn"


def _worst_move(game: Game) -> Move | None:
    errs = [m for m in game.moves if m.phase == ENDGAME and m.classification in ERRORS]
    return max(errs, key=lambda m: m.drop) if errs else None


def endgames(games: list[Game], level: dict | None) -> dict:
    reached = [(g, g.boundaries[ENDGAME]) for g in games if g.boundaries.get(ENDGAME) is not None]
    by_type: dict[str, list[Game]] = defaultdict(list)
    winning, worse = [], []
    for g, i in reached:
        by_type[endgame_type(g.positions[i])].append(g)
        if g.win_graph[i] >= WINNING_WIN:
            winning.append(g)
        elif g.win_graph[i] <= 100.0 - WINNING_WIN:
            worse.append(g)
    rows = [{"type": t, "name": TYPE_NAMES[t], **record(gs), "accuracy": mean([g.phase_accuracy.get(ENDGAME) for g in gs if g.phase_accuracy.get(ENDGAME) is not None])}
            for t, gs in by_type.items()]
    rows.sort(key=lambda r: -r["games"])
    thrown = [g for g in winning if g.outcome != "win"]
    thrown_moves = [(g, m) for g in thrown if (m := _worst_move(g))]
    worst_throw = max(thrown_moves, key=lambda gm: gm[1].drop) if thrown_moves else None
    conversion = {"games": len(winning), "won": len(winning) - len(thrown), "rate": round(100 * (len(winning) - len(thrown)) / len(winning)),
                  "drop_per_game": round(sum(m.drop for _, m in thrown_moves) / max(1, len(games)), 1), "example": example(*worst_throw) if worst_throw else None} if winning else None
    held = [g for g in worse if g.outcome != "loss"]
    hold = {"games": len(worse), "held": len(held), "rate": round(100 * len(held) / len(worse))} if worse else None
    lose_most = max((r for r in rows if r["games"] >= MIN_GAMES), key=lambda r: (r["losses"] / r["games"], r["losses"]), default=None)
    if lose_most and lose_most["losses"] == 0:
        lose_most = None
    finding = None
    if conversion and conversion["games"] >= MIN_GAMES:
        finding = f"You converted {conversion['won']} of {conversion['games']} winning endgames."
    if lose_most:
        finding = (finding + " " if finding else "") + f"You lose most in {TYPE_NAMES[lose_most['type']]}s: {lose_most['losses']} of {lose_most['games']}."
    focus = lose_most["type"] if lose_most else (endgame_type(thrown[0].positions[thrown[0].boundaries[ENDGAME]]) if thrown else None)
    action = resources.endgame_drill(focus, "promote" if conversion and thrown else None) if focus else None
    lesson = resources.lesson_for(resources.ENDGAME_TYPES[focus][1]) if focus else None
    return {"games": len(reached), "needs": max(0, MIN_GAMES - len(reached)), "types": rows, "conversion": conversion, "hold": hold,
            "lose_most": lose_most["type"] if lose_most else None, "finding": finding,
            "action": action or lesson or resources.lesson_in("endgame", resources.band_of(level)), "lesson": lesson,
            "bot": resources.bot(ENDGAME, resources.ENDGAME_TYPES[focus][0] if focus else None, resources.rating_of(level))}
