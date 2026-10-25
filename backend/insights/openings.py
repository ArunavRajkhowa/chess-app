"""Opening findings: per opening and colour, how you score, where you leave the book and what it
costs, the move you get wrong again and again, and the course that covers the line."""
from __future__ import annotations

from collections import Counter, defaultdict

from ..review import classify as C
from . import resources
from .games import ERRORS, PROBLEM, Game, Move, example, fen_key, mean, record

MIN_GAMES = 2  # one game is a game; two make a row worth reading
MIN_REPEATS = 2


def deviation(game: Game) -> Move | None:
    """The player's first move out of the book, or None when the opponent left it first."""
    if not game.opening:
        return None
    return game.move_at(game.opening["last_book_ply"] + 1)


def first_error(game: Game) -> Move | None:
    return next((m for m in game.moves if m.classification in ERRORS), None)


def repeated_mistakes(games: list[Game]) -> list[dict]:
    """Positions where the player went wrong in two games or more (same position, move counters ignored)."""
    by_fen: dict[str, list[tuple[Game, Move]]] = defaultdict(list)
    for g in games:
        for m in g.moves:
            if m.classification in PROBLEM:
                by_fen[fen_key(m.fen)].append((g, m))
    out = []
    for hits in by_fen.values():
        if len(hits) < MIN_REPEATS:
            continue
        g, m = max(hits, key=lambda gm: gm[1].drop)
        out.append({
            "times": len(hits), "played_san": Counter(x.san for _, x in hits).most_common(1)[0][0], "best_san": m.best_san,
            "opening": g.opening["name"] if g.opening else None, "drop_total": round(sum(x.drop for _, x in hits), 1), "example": example(g, m),
        })
    return sorted(out, key=lambda r: -r["drop_total"])


def _row(name: str, color: str, games: list[Game]) -> dict:
    devs = [(g, m) for g in games if (m := deviation(g))]
    costly = [(g, m) for g, m in devs if m.drop > C.GOOD_MAX_DROP]
    firsts = [m for g in games if (m := first_error(g))]
    repeated = repeated_mistakes(games)
    leave = None
    if devs:
        worst = max(costly, key=lambda gm: gm[1].drop) if costly else None
        leave = {"ply": mean([m.ply for _, m in devs]), "move_number": mean([m.move_number for _, m in devs]), "games": len(devs),
                 "costly": len(costly), "drop_total": round(sum(m.drop for _, m in costly), 1), "example": example(*worst) if worst else None}
    return {
        "name": name, "eco": next((g.opening["eco"] for g in games if g.opening), None), "color": color, **record(games),
        "accuracy": mean([g.accuracy for g in games if g.accuracy is not None]),
        "leave_book": leave, "first_mistake_move": mean([m.move_number for m in firsts]),
        "repeated": repeated[0] if repeated else None, "course": resources.course_for(name, color),
    }


def openings(games: list[Game], level: dict | None) -> dict:
    band, rating = resources.band_of(level), resources.rating_of(level)
    groups: dict[tuple[str, str], list[Game]] = defaultdict(list)
    for g in games:
        if g.opening:
            groups[(g.opening["name"], g.color)].append(g)
    rows = sorted((_row(n, c, gs) for (n, c), gs in groups.items() if len(gs) >= MIN_GAMES), key=lambda r: -r["games"])
    repeated = repeated_mistakes(games)
    worst = min(rows, key=lambda r: (r["score"], -r["games"])) if rows else None
    finding = None
    if repeated:
        r = repeated[0]
        finding = f"You have gone wrong in the same position {r['times']} times: {r['played_san']} instead of {r['best_san']}" + (f" in the {r['opening']}." if r["opening"] else ".")
    elif worst:
        finding = f"As {worst['color'].capitalize()} in the {worst['name']} you score {worst['score']}% over {worst['games']} games."
    action = (worst and worst["course"]) or resources.lesson_in("opening", band)
    return {"rows": rows[:8], "repeated": repeated[:5], "needs": max(0, MIN_GAMES - max((len(gs) for gs in groups.values()), default=0)),
            "finding": finding, "action": action,
            "bot": resources.bot("opening", worst["course"]["id"] if worst and worst["course"] else None, rating) if worst else None}
