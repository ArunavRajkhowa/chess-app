"""Insights API: what the reviewed games say about the player. Everything comes from stored reviews
and puzzle attempts; a stat with no data is null, never a made-up zero."""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from fastapi import APIRouter

from ..review import classify as C
from ..storage.db import database

router = APIRouter(prefix="/api/insights", tags=["insights"])

SHAPES = {
    "smooth": "One side's advantage grew steadily; never in doubt.",
    "balanced": "Close to equal almost throughout; decided late.",
    "sharp": "Big swings both ways; tactics decided it.",
    "sudden": "Level until one blunder decided it.",
    "giveaway": "One side was winning and then lost it.",
    "wild": "The lead changed hands repeatedly.",
}


def _shape(graph: list[float]) -> str:
    if len(graph) < 6:
        return "balanced"
    swings = sum(1 for a, b in zip(graph, graph[1:]) if abs(a - b) >= 15)
    lead_changes = sum(1 for a, b in zip(graph, graph[1:]) if (a - 50) * (b - 50) < 0 and abs(a - b) >= 8)
    peak = max(graph)
    trough = min(graph)
    if lead_changes >= 3 and swings >= 3:
        return "wild"
    if (peak >= 85 and graph[-1] <= 30) or (trough <= 15 and graph[-1] >= 70):
        return "giveaway"
    if swings >= 3:
        return "sharp"
    if swings == 1 and (graph[-1] >= 85 or graph[-1] <= 15):
        return "sudden"
    if max(abs(g - 50) for g in graph[: len(graph) * 2 // 3]) <= 15:
        return "balanced"
    return "smooth"


@router.get("/me")
async def me() -> dict:
    rows = await database.fetch_all(
        "SELECT r.game_id, r.report_json, g.player_color, g.result, g.termination, g.opening_name, g.opening_eco, g.bot_id, g.source, g.created_at "
        "FROM reviews r JOIN games g ON g.id = r.game_id WHERE g.source = 'bot' ORDER BY r.created_at DESC LIMIT 200"
    )
    if not rows:
        return {"games": 0, "message": "Play and review a few games to see your patterns."}
    accuracies: list[float] = []
    acc_by_phase: dict[str, list[float]] = defaultdict(list)
    counts: Counter = Counter()
    openings: dict[str, dict] = {}
    results = Counter()
    endings = Counter()
    shapes = Counter()
    timeline = []
    worst_moves: list[dict] = []
    phase_games_ended = Counter()
    for r in rows:
        rep = json.loads(r["report_json"])
        me_side = rep[r["player_color"]]
        accuracies.append(me_side["accuracy"])
        timeline.append({"at": r["created_at"], "accuracy": me_side["accuracy"], "game_id": r["game_id"]})
        for ph, v in me_side["phase_accuracy"].items():
            if v is not None:
                acc_by_phase[ph].append(v)
        for k, v in me_side["counts"].items():
            counts[k] += v
        won = r["result"] in ("1-0", "0-1") and (r["result"] == "1-0") == (r["player_color"] == "white")
        outcome = "draw" if r["result"] == "1/2-1/2" else ("win" if won else "loss")
        results[outcome] += 1
        endings[f"{outcome}:{r['termination'] or 'unknown'}"] += 1
        op = r["opening_name"] or "Unknown"
        d = openings.setdefault(op, {"name": op, "eco": r["opening_eco"], "games": 0, "wins": 0, "draws": 0, "losses": 0, "accuracy": []})
        d["games"] += 1
        d[{"win": "wins", "draw": "draws", "loss": "losses"}[outcome]] += 1
        d["accuracy"].append(me_side["accuracy"])
        shapes[_shape(rep["eval_graph"])] += 1
        if rep["moves"]:
            phase_games_ended[rep["moves"][-1]["phase"]] += 1
        for m in rep["moves"]:
            if m["color"] == r["player_color"] and m["classification"] in (C.BLUNDER, C.MISS):
                worst_moves.append({"game_id": r["game_id"], "ply": m["ply"], "san": m["san"], "best": m["best_move_san"], "drop": round(m["win_before"] - m["win_after"], 1), "phase": m["phase"], "classification": m["classification"]})
    n = len(rows)
    total_moves = sum(counts.values()) or 1
    opening_list = []
    for d in openings.values():
        d["accuracy"] = round(sum(d["accuracy"]) / len(d["accuracy"]), 1)
        opening_list.append(d)
    opening_list.sort(key=lambda d: -d["games"])
    phase_acc = {k: round(sum(v) / len(v), 1) for k, v in acc_by_phase.items()}
    weakest_phase = min(phase_acc, key=phase_acc.get) if phase_acc else None
    work_on = []
    if weakest_phase:
        work_on.append({"area": weakest_phase, "why": f"Your {weakest_phase} accuracy ({phase_acc[weakest_phase]}%) is your lowest.", "action": {"opening": "Study your most played openings in Openings and play through model games.", "middlegame": "Do themed puzzles and the strategy lessons in Learn.", "endgame": "Run the endgame drills in Learn and the endgame puzzles."}[weakest_phase]})
    blunder_rate = counts[C.BLUNDER] / n
    if blunder_rate >= 1:
        work_on.append({"area": "blunders", "why": f"{blunder_rate:.1f} blunders per game.", "action": "Before every move, check the opponent's checks, captures and threats. Use Coach mode with threat arrows."})
    if counts[C.MISS] >= max(2, n // 3):
        work_on.append({"area": "missed wins", "why": f"{counts[C.MISS]} winning chances missed.", "action": "Solve 'crushing' and mate puzzles daily to sharpen pattern recognition."})
    return {
        "games": n,
        "accuracy": {"mean": round(sum(accuracies) / n, 1), "best": max(accuracies), "worst": min(accuracies), "timeline": list(reversed(timeline))},
        "results": dict(results), "endings": dict(endings), "phase_accuracy": phase_acc, "phase_games_ended": dict(phase_games_ended),
        "move_quality": {k: {"count": counts[k], "per_game": round(counts[k] / n, 2), "share": round(100 * counts[k] / total_moves, 1)} for k in C.ALL_CLASSES},
        "openings": opening_list[:10], "shapes": {k: {"count": v, "description": SHAPES[k]} for k, v in shapes.items()},
        "worst_moves": sorted(worst_moves, key=lambda m: -m["drop"])[:10], "work_on": work_on,
    }
