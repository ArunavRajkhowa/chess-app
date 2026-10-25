"""Move-quality findings: the last 10 games against the 10 before, the phase where quality drops,
where in the game blunders cluster, time controls, and your centipawn loss against your band's."""
from __future__ import annotations

from collections import defaultdict

from ..content.lessons import BANDS
from ..review import classify as C
from ..review.phases import ENDGAME, MIDDLEGAME, OPENING
from . import resources
from .games import ERRORS, Game, example, mean

SHORT = 10
TREND_MIN_GAMES = 2 * SHORT  # a trend needs the last ten and the ten before them
TREND_STEP = 2.0  # accuracy points between those two windows that count as a change
BUCKET_MOVES = 10
MIN_PHASE_MOVES = 20
MIN_CLUSTER_BLUNDERS = 2
MIN_TIME_CONTROL_GAMES = 2
ACPL_SOURCE = "the review's rating table (backend/review/classify.py)"
TABLE_FLOOR, TABLE_CEILING = 400, 2800  # the ratings the table spans


def band_bounds(band: int) -> tuple[int, int]:
    lo = next((b["max_rating"] for b in BANDS if b["band"] == band - 1), None) or TABLE_FLOOR
    hi = next((b["max_rating"] for b in BANDS if b["band"] == band), None) or TABLE_CEILING
    return lo, hi


def window(games: list[Game]) -> dict | None:
    acc = [g.accuracy for g in games if g.accuracy is not None]
    if not acc:
        return None
    n = len(games)
    return {"games": n, "accuracy": mean(acc), "acpl": mean([g.acpl for g in games if g.acpl is not None]),
            "blunders_per_game": round(sum(g.counts[C.BLUNDER] for g in games) / n, 2), "misses_per_game": round(sum(g.counts[C.MISS] for g in games) / n, 2)}


def trend(games: list[Game]) -> dict:
    if len(games) < TREND_MIN_GAMES:
        return {"direction": None, "delta": None, "needs": TREND_MIN_GAMES - len(games)}
    last, before = window(games[-SHORT:]), window(games[-2 * SHORT : -SHORT])
    if not last or not before:
        return {"direction": None, "delta": None, "needs": 0}
    delta = round(last["accuracy"] - before["accuracy"], 1)
    return {"direction": "up" if delta >= TREND_STEP else "down" if delta <= -TREND_STEP else "flat", "delta": delta, "needs": 0}


def phases(games: list[Game]) -> dict:
    out = {}
    n = max(1, len(games))
    for ph in (OPENING, MIDDLEGAME, ENDGAME):
        moves = [m for g in games for m in g.moves if m.phase == ph]
        if not moves:
            out[ph] = None
            continue
        errs = [m for m in moves if m.classification in ERRORS]
        out[ph] = {"moves": len(moves), "accuracy": mean([g.phase_accuracy.get(ph) for g in games if g.phase_accuracy.get(ph) is not None]),
                   "acpl": round(sum(min(m.cp_loss, C.ACPL_CP_CAP) for m in moves) / len(moves), 1), "errors": len(errs),
                   "drop_per_game": round(sum(m.drop for m in errs) / n, 1)}
    return out


def clusters(games: list[Game]) -> dict:
    buckets: dict[int, dict] = defaultdict(lambda: {"moves": 0, "blunders": 0, "drop": 0.0, "worst": None})
    for g in games:
        for m in g.moves:
            b = buckets[(m.move_number - 1) // BUCKET_MOVES]
            b["moves"] += 1
            if m.classification == C.BLUNDER:
                b["blunders"] += 1
                b["drop"] += m.drop
                if b["worst"] is None or m.drop > b["worst"][1].drop:
                    b["worst"] = (g, m)
    peak_key = max(buckets, key=lambda k: (buckets[k]["blunders"] / buckets[k]["moves"], buckets[k]["blunders"]), default=None)
    peak = None
    if peak_key is not None and buckets[peak_key]["blunders"] >= MIN_CLUSTER_BLUNDERS:
        b = buckets[peak_key]
        peak = {"from_move": peak_key * BUCKET_MOVES + 1, "to_move": (peak_key + 1) * BUCKET_MOVES, "blunders": b["blunders"], "moves": b["moves"],
                "drop_total": round(b["drop"], 1), "example": example(*b["worst"])}
    return {"peak": peak}


def time_controls(games: list[Game]) -> list[dict] | None:
    by_tc: dict[str, list[Game]] = defaultdict(list)
    for g in games:
        by_tc[g.time_control or "no clock"].append(g)
    rows = [{"time_control": tc, **w} for tc, gs in by_tc.items() if len(gs) >= MIN_TIME_CONTROL_GAMES and (w := window(gs))]
    return sorted(rows, key=lambda r: -r["games"]) if len(rows) >= 2 else None


def band_comparison(games: list[Game], level: dict | None) -> dict | None:
    acpl = mean([g.acpl for g in games if g.acpl is not None])
    if not level or acpl is None:
        return None
    lo, hi = band_bounds(level["band"])
    expected_hi, expected_lo = C.acpl_for_rating(lo), C.acpl_for_rating(hi)  # a lower rating loses more
    verdict = "better" if acpl < expected_lo else "worse" if acpl > expected_hi else "as expected"
    return {"acpl": acpl, "expected_low": expected_lo, "expected_high": expected_hi, "verdict": verdict, "source": ACPL_SOURCE}


def quality(games: list[Game], level: dict | None) -> dict:
    band = level["band"] if level else None
    ph = phases(games)
    weakest = min((k for k, v in ph.items() if v and v["moves"] >= MIN_PHASE_MOVES), key=lambda k: ph[k]["accuracy"] if ph[k]["accuracy"] is not None else 101, default=None)
    tr = trend(games)
    cl = clusters(games)
    finding = None
    if weakest:
        finding = f"Your {weakest} accuracy ({ph[weakest]['accuracy']}%) is your lowest; mistakes there cost you {ph[weakest]['drop_per_game']}% win chance per game."
    if cl["peak"]:
        finding = (finding + " " if finding else "") + f"Your blunders cluster at moves {cl['peak']['from_move']}–{cl['peak']['to_move']}: {cl['peak']['blunders']} of them."
    return {
        "recent": window(games[-SHORT:]), "trend": tr, "phases": ph, "weakest_phase": weakest,
        "clusters": cl, "time_controls": time_controls(games), "band": band_comparison(games, level),
        "finding": finding, "action": resources.lesson_in("thinking", band), "bot": resources.bot("defence", None, None),
    }
