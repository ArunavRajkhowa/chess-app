"""Who the coach is talking to and what happened in this game, read from the store so the
answer fits the player and the moment. Absence is data: a field with nothing behind it is None."""
from __future__ import annotations

from collections import Counter

import chess
from fastapi import HTTPException

from ..bots.roster import find_bot
from ..content.lessons import BANDS, find_lesson
from ..insights.build import build as insights
from ..review import classify as C
from ..review.jobs import stored_report
from ..storage import games as store
from .facts import eval_trend

PROBLEM_CLASSES = (C.INACCURACY, C.MISTAKE, C.MISS, C.BLUNDER)
# Coach wording level for each band in content/lessons.py; the ratings live only in BANDS.
LEVEL_BY_BAND = {0: "beginner", 1: "beginner", 2: "beginner", 3: "intermediate", 4: "intermediate", 5: "advanced", 6: "advanced"}
MISSED_THEMES = 3


def level_for_band(band: int) -> str:
    return LEVEL_BY_BAND.get(band, "master")


def bot_brief(bot_id: str | None) -> dict | None:
    """The bot's name, rating and tier, or None for no bot or a bot no longer in the roster."""
    bot = find_bot(bot_id) if bot_id else None
    return {"name": bot.name, "elo": bot.elo, "tier": bot.tier} if bot else None


async def player_context(player: str) -> dict:
    """The player's level and patterns: puzzle rating, band, weakest phase, blunder rate, missed motifs."""
    from ..routers.learn import player_level  # at call time: the routers package imports this module
    from ..routers.puzzles import due_puzzles

    lvl = await player_level(player)
    ins = await insights(player)
    missed = Counter(t for p in (await due_puzzles(player))["puzzles"] for t in p.get("themes", []))
    reviewed = ins["games"]
    quality = ins.get("move_quality") or {}
    return {
        "puzzle_rating": lvl["puzzle_rating"] if lvl else None,
        "band": next((b["subtitle"] for b in BANDS if b["band"] == lvl["band"]), None) if lvl else None,
        "level": level_for_band(lvl["band"]) if lvl else None,
        "reviewed_games": reviewed,
        "weakest_phase": ((ins.get("sections") or {}).get("quality") or {}).get("weakest_phase"),
        "blunders_per_game": quality[C.BLUNDER]["per_game"] if quality else None,
        "focus": (ins.get("focus") or {}).get("goal"),
        "most_missed_motif_in_games": ((ins.get("sections") or {}).get("tactics") or {}).get("most_missed"),
        "missed_puzzle_themes": [t for t, _ in missed.most_common(MISSED_THEMES)],
    }


async def game_context(player: str, game_id: str, board: chess.Board, ply: int | None = None) -> dict:
    """This game up to the board (or `ply` moves in when known): the bot, the clock, the moves with
    their review labels, earlier mistakes. Without `ply` a repeated position counts at its last occurrence."""
    row = await store.read_game(player, game_id)
    if not row:
        raise HTTPException(404, f"game_id {game_id!r}: no such game")
    report = await stored_report(player, game_id)
    moves = row["moves"]
    start = row.get("start_fen") or chess.STARTING_FEN
    key = " ".join(board.fen().split()[:4])
    found = ply if ply is not None else next((i + 1 for i in range(len(moves) - 1, -1, -1) if " ".join(moves[i]["fen"].split()[:4]) == key), None)
    if found is None and " ".join(start.split()[:4]) == key:
        found = 0
    cut = len(moves) if found is None else found  # a position off the game line: the whole game, but no last move
    labels = report["moves"][:cut] if report else []
    mine = row["player_color"]
    text, mistakes = [], []
    walk = chess.Board(start)
    for i, m in enumerate(moves[:cut]):
        prefix = f"{walk.fullmove_number}." if walk.turn == chess.WHITE else f"{walk.fullmove_number}..." if i == 0 else ""
        walk.push_uci(m["uci"])
        rm = labels[i] if i < len(labels) else None
        if rm and rm["color"] == mine and rm["classification"] in PROBLEM_CLASSES:
            text.append(f"{prefix}{m['san']} ({rm['classification']}; {rm['best_move_san']} was better)")
            mistakes.append({"move_number": rm["move_number"], "san": rm["san"], "classification": rm["classification"], "best": rm["best_move_san"]})
        else:
            text.append(f"{prefix}{m['san']}")
    return {
        "last_move_uci": moves[found - 1]["uci"] if found else None,
        "positions": [start] + [m["fen"] for m in moves[:cut]],
        "played": [m["san"] for m in moves[:cut]],
        "player_color": mine,
        "bot": bot_brief(row.get("bot_id")),
        "time_control": row.get("time_control"),
        "moves_so_far": " ".join(text),
        "earlier_mistakes": mistakes,
        "eval_trend": eval_trend(report["eval_graph"][:cut + 1]) if report else None,
        "reviewed": report is not None,
    }


def lesson_context(lesson_id: str) -> dict:
    lsn = find_lesson(lesson_id)
    if not lsn:
        raise HTTPException(404, f"lesson_id {lesson_id!r}: no such lesson")
    return {"title": lsn.title, "objective": lsn.objective, "band": lsn.band, "strand": lsn.strand}


async def coach_context(player: str, board: chess.Board, *, game_id: str | None = None, ply: int | None = None,
                        lesson_id: str | None = None) -> dict:
    return {
        "player": await player_context(player),
        "game": await game_context(player, game_id, board, ply) if game_id else None,
        "lesson": lesson_context(lesson_id) if lesson_id else None,
    }
