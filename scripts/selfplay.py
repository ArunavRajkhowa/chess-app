"""Plays bot-versus-bot games to seed the puzzle generator with tactical positions.
Usage: python -m scripts.selfplay --games 40 --out data/selfplay/games.pgn"""
from __future__ import annotations

import argparse
import asyncio
import random
from pathlib import Path

import chess
import chess.pgn

from backend.bots.roster import BOTS
from backend.bots.selector import choose_move
from backend.engine.pool import EnginePool


async def play_one(pool: EnginePool, rng: random.Random, max_plies: int = 120) -> chess.pgn.Game:
    weak = [b for b in BOTS if 400 <= b.elo <= 1600]
    white, black = rng.sample(weak, 2)
    board = chess.Board()
    game = chess.pgn.Game()
    game.headers["Event"] = "Chess Coach self-play"
    game.headers["White"] = f"{white.name} ({white.elo})"
    game.headers["Black"] = f"{black.name} ({black.elo})"
    node = game
    while not board.is_game_over(claim_draw=True) and board.ply() < max_plies:
        bot = white if board.turn == chess.WHITE else black
        choice = await choose_move(board, bot, pool, rng)
        board.push(choice.move)
        node = node.add_variation(choice.move)
    game.headers["Result"] = board.result(claim_draw=True)
    return game


async def main(n: int, out: Path, seed: int) -> None:
    pool = EnginePool()
    await pool.start()
    rng = random.Random(seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with out.open("a", encoding="utf-8") as fh:
            for i in range(n):
                game = await play_one(pool, rng)
                fh.write(str(game) + "\n\n")
                fh.flush()
                print(f"game {i + 1}/{n}: {game.headers['White']} vs {game.headers['Black']} {game.headers['Result']} ({game.end().ply()} plies)")
    finally:
        await pool.stop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=20)
    ap.add_argument("--out", default="data/selfplay/games.pgn")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    asyncio.run(main(a.games, Path(a.out), a.seed))
