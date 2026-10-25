"""The whole Insights response for one player: the games loaded once, every section's rule run over
them, the plan derived from the sections; kept per player until a review or a puzzle attempt lands."""
from __future__ import annotations

import asyncio
import logging
import time

from ..content.lessons import BANDS
from ..review import classify as C
from ..storage.db import database
from .endgames import endgames
from .games import Game, load_games, mean
from .middlegame import middlegame
from .openings import openings
from .plan import plan
from .quality import quality
from .strengths import puzzle_strengths, strengths
from .summary import summary
from .tactics import tactics

LOGGER = logging.getLogger("chess.insights")
MIN_GAMES_FOR_ESTIMATE = 3  # fewer review estimates than this and the level is not placed from them
_CACHE: dict[str, tuple[str, dict]] = {}
_CACHE_CAP = 500


def level_of(games: list[Game], puzzle: dict | None) -> dict | None:
    """The player's band from the settled puzzle rating, else from the reviews' rating estimates."""
    from ..routers.learn import band_for_rating  # at call time: the routers package imports this one

    if puzzle:
        rating, source = puzzle["puzzle_rating"], "puzzle rating"
    else:
        estimates = [g.estimated_rating for g in games if g.estimated_rating is not None]
        if len(estimates) < MIN_GAMES_FOR_ESTIMATE:
            return None
        rating, source = round(mean(estimates, 0)), "review estimate"
    band = band_for_rating(rating)
    info = BANDS[band]
    return {"band": band, "name": info["name"], "rating": rating, "range": info["rating"], "source": source}


def build_findings(games: list[Game], level: dict | None, puzzle_strong: list[dict]) -> dict:
    band = level["band"] if level else None
    sections = {
        "games": len(games),
        "openings": openings(games, level), "middlegame": middlegame(games, level), "endgames": endgames(games, level),
        "quality": quality(games, level), "tactics": tactics(games, level),
    }
    sections["strengths"] = strengths(sections, sections["quality"]["band"]) + puzzle_strong
    items = plan(sections, band)
    hint = None if level else f"settle a puzzle rating or review {MIN_GAMES_FOR_ESTIMATE} games with {C.MIN_MOVES_FOR_ESTIMATE} moves"
    return {**summary(games), "level": level, "level_hint": hint, "trend": sections["quality"]["trend"], "focus": items[0] if items else None,
            "sections": {k: v for k, v in sections.items() if k != "games"}, "plan": items}


async def build(player: str) -> dict:
    t0 = time.perf_counter()
    games = await load_games(player)
    if not games:
        return {"games": 0, "message": "Play and review a few games to see your patterns."}
    from ..routers.learn import player_level  # at call time: the routers package imports this one

    puzzle = await player_level(player)
    marks = await database.fetch_one(
        "SELECT (SELECT MAX(r.created_at) FROM reviews r JOIN games g ON g.id = r.game_id WHERE g.player_id = ? AND g.source = 'bot') AS reviewed, "
        "(SELECT MAX(id) FROM puzzle_attempts WHERE player_id = ?) AS attempt", (player, player))
    key = f"{len(games)}:{games[-1].id}:{marks['reviewed']}:{marks['attempt']}:{puzzle}"  # a re-review or a puzzle attempt changes it
    hit = _CACHE.get(player)
    if hit and hit[0] == key:
        return hit[1]
    puzzle_strong = await puzzle_strengths(player)
    out = await asyncio.to_thread(build_findings, games, level_of(games, puzzle), puzzle_strong)  # CPU work: off the event loop
    if len(_CACHE) >= _CACHE_CAP:
        _CACHE.clear()
    _CACHE[player] = (key, out)
    LOGGER.info("insights built games=%d plan=%d ms=%d", len(games), len(out["plan"]), round(1000 * (time.perf_counter() - t0)))
    return out
