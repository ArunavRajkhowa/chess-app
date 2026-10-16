"""Awards: achievements computed from what the store already holds. Nothing is awarded by a flag;
every badge is a query, so it can never be out of date."""
from __future__ import annotations

from fastapi import APIRouter

from ..bots.roster import BOTS_BY_ID
from ..storage.db import database

router = APIRouter(prefix="/api/awards", tags=["awards"])


async def _facts() -> dict:
    games = await database.fetch_all("SELECT bot_id, player_color, result, status FROM games WHERE source = 'bot' AND status = 'finished'")
    wins = [g for g in games if g["result"] in ("1-0", "0-1") and (g["result"] == "1-0") == (g["player_color"] == "white")]
    tiers_beaten = {BOTS_BY_ID[g["bot_id"]].tier for g in wins if g["bot_id"] in BOTS_BY_ID}
    puzzles = await database.fetch_one("SELECT COUNT(*) AS n, SUM(solved) AS s FROM puzzle_attempts WHERE mode = 'rated'")
    lessons = await database.fetch_one("SELECT COUNT(*) AS n FROM lesson_progress WHERE completed_at IS NOT NULL")
    reviews = await database.fetch_one("SELECT COUNT(*) AS n FROM reviews")
    rush = max([await database.get_player_value(f"rush_best_{m}", 0) for m in ("3m", "5m", "survival")] or [0])
    dates = await database.get_player_value("daily_solved_dates", [])
    rating = await database.get_player_value("puzzle_rating", None)
    endgames = await database.get_player_value("endgame_stats", {})
    return {
        "games": len(games), "wins": len(wins), "tiers_beaten": tiers_beaten,
        "puzzles_solved": int(puzzles["s"] or 0), "puzzles_tried": int(puzzles["n"] or 0),
        "lessons_done": int(lessons["n"] or 0), "reviews": int(reviews["n"] or 0), "rush_best": rush,
        "daily_days": len(dates), "puzzle_rating": rating["rating"] if rating else None,
        "endgames_solved": sum(1 for v in endgames.values() if v.get("solved")),
    }


AWARDS = [
    ("first-game", "First game", "Finish a game against a bot", lambda f: f["games"] >= 1),
    ("first-win", "First win", "Beat any bot", lambda f: f["wins"] >= 1),
    ("beginner-slayer", "Beginner slayer", "Beat a beginner bot", lambda f: "beginner" in f["tiers_beaten"]),
    ("club-strength", "Club strength", "Beat an intermediate bot", lambda f: "intermediate" in f["tiers_beaten"]),
    ("expert", "Expert", "Beat an advanced bot", lambda f: "advanced" in f["tiers_beaten"]),
    ("giant-killer", "Giant killer", "Beat a master bot", lambda f: "master" in f["tiers_beaten"]),
    ("ten-games", "Ten games", "Finish ten games", lambda f: f["games"] >= 10),
    ("fifty-games", "Fifty games", "Finish fifty games", lambda f: f["games"] >= 50),
    ("first-review", "Student of the game", "Review a game", lambda f: f["reviews"] >= 1),
    ("ten-reviews", "Analyst", "Review ten games", lambda f: f["reviews"] >= 10),
    ("tactics-newbie", "Tactics newbie", "Solve a rated puzzle", lambda f: f["puzzles_solved"] >= 1),
    ("tactics-50", "Puzzle regular", "Solve fifty rated puzzles", lambda f: f["puzzles_solved"] >= 50),
    ("tactics-500", "Puzzle veteran", "Solve five hundred rated puzzles", lambda f: f["puzzles_solved"] >= 500),
    ("rated-1500", "1500 club", "Reach a 1500 puzzle rating", lambda f: (f["puzzle_rating"] or 0) >= 1500),
    ("rated-2000", "2000 club", "Reach a 2000 puzzle rating", lambda f: (f["puzzle_rating"] or 0) >= 2000),
    ("rush-10", "Rush starter", "Score 10 in Puzzle Rush", lambda f: f["rush_best"] >= 10),
    ("rush-25", "Rush runner", "Score 25 in Puzzle Rush", lambda f: f["rush_best"] >= 25),
    ("daily-7", "One week", "Solve the daily puzzle on seven days", lambda f: f["daily_days"] >= 7),
    ("daily-30", "One month", "Solve the daily puzzle on thirty days", lambda f: f["daily_days"] >= 30),
    ("first-lesson", "First lesson", "Complete a lesson", lambda f: f["lessons_done"] >= 1),
    ("ten-lessons", "Diligent", "Complete ten lessons", lambda f: f["lessons_done"] >= 10),
    ("endgame-5", "Technician", "Solve five endgame drills", lambda f: f["endgames_solved"] >= 5),
]


@router.get("")
async def awards() -> dict:
    f = await _facts()
    out = [{"key": k, "name": n, "how": h, "earned": bool(test(f))} for k, n, h, test in AWARDS]
    return {"awards": out, "earned": sum(1 for a in out if a["earned"]), "total": len(out), "facts": {k: (sorted(v) if isinstance(v, set) else v) for k, v in f.items()}}
