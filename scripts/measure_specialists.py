"""Measures how long each opening specialist stays in its family: self-play games (the bot on both
sides) counting the plies before the position leaves the family's named lines.
Usage: python -m scripts.measure_specialists [--games 5] [--plies 24]"""
from __future__ import annotations

import argparse
import asyncio
import random
import statistics

import chess

from backend.bots.roster import SPECIALTY_OPENING, Bot
from backend.bots.selector import _favourite_positions, choose_move
from backend.bots.specialists import specialist_bots
from backend.engine.pool import EnginePool
from backend.openings.courses import load_courses


async def plies_in_family(pool: EnginePool, bot: Bot, family_prefixes: list[str], max_plies: int, rng: random.Random) -> int:
    """Plies played while every position lies on a named book line of the course's openings."""
    on_family = _favourite_positions(tuple(family_prefixes))  # the selector's own set: every position on those lines
    board = chess.Board()
    while board.ply() < max_plies and not board.is_game_over():
        choice = await choose_move(board, bot, pool, rng)
        board.push(choice.move)
        if board.epd() not in on_family:
            return board.ply() - 1
    return board.ply()


async def main(games: int, max_plies: int) -> None:
    pool = EnginePool()
    await pool.start()
    rng = random.Random(1)
    courses = load_courses()
    try:
        for bot in specialist_bots().values():
            if not bot.specialty or bot.specialty.kind != SPECIALTY_OPENING:
                continue
            prefixes = courses[bot.specialty.key].openings
            counts = [await plies_in_family(pool, bot, prefixes, max_plies, rng) for _ in range(games)]
            print(f"{bot.id:36s} plies in family over {games} games: {counts} mean {statistics.mean(counts):.1f}")
    finally:
        await pool.stop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=5)
    ap.add_argument("--plies", type=int, default=24)
    a = ap.parse_args()
    asyncio.run(main(a.games, a.plies))
