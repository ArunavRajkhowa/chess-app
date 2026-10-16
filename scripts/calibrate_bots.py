"""Measures each bot's strength by playing it against Stockfish limited to a fixed Elo
(UCI_LimitStrength) and estimating a performance rating from the score. Writes
data/bot_calibration.json. Usage: python -m scripts.calibrate_bots --games 4 [--bots pip,max]"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
from pathlib import Path

import chess
import chess.engine

from backend.bots.roster import BOTS, Bot
from backend.bots.selector import choose_move
from backend.engine.locator import find_engine_command
from backend.engine.pool import EnginePool

REFERENCE_MOVETIME_SECONDS = 0.1
MIN_UCI_ELO, MAX_UCI_ELO = 1320, 3190
MAX_PLIES = 160


async def play_game(pool: EnginePool, ref: chess.engine.Protocol, bot: Bot, bot_is_white: bool, rng: random.Random) -> float:
    board = chess.Board()
    while not board.is_game_over(claim_draw=True) and board.ply() < MAX_PLIES:
        if board.turn == (chess.WHITE if bot_is_white else chess.BLACK):
            choice = await choose_move(board, bot, pool, rng)
            board.push(choice.move)
        else:
            res = await ref.play(board, chess.engine.Limit(time=REFERENCE_MOVETIME_SECONDS))
            board.push(res.move)
    result = board.result(claim_draw=True)
    if result == "1/2-1/2" or result == "*":
        return 0.5
    return 1.0 if (result == "1-0") == bot_is_white else 0.0


def performance(ref_elo: int, score: float, n: int) -> int:
    p = min(max(score / n, 0.02), 0.98)
    return int(round(ref_elo + 400 * math.log10(p / (1 - p))))


async def main(games: int, only: list[str] | None, out: Path, seed: int) -> None:
    pool = EnginePool()
    await pool.start()
    _, ref = await chess.engine.popen_uci(find_engine_command())
    rng = random.Random(seed)
    rows: list[dict] = []
    try:
        for bot in BOTS:
            if only and bot.id not in only:
                continue
            ref_elo = min(max(bot.elo, MIN_UCI_ELO), MAX_UCI_ELO)
            await ref.configure({"UCI_LimitStrength": True, "UCI_Elo": ref_elo})
            score = 0.0
            for g in range(games):
                score += await play_game(pool, ref, bot, bot_is_white=(g % 2 == 0), rng=rng)
            est = performance(ref_elo, score, games)
            rows.append({"bot": bot.id, "label_elo": bot.elo, "reference_elo": ref_elo, "games": games, "score": score, "estimated_elo": est})
            print(f"{bot.name:12s} label {bot.elo:5d}  vs SF@{ref_elo}: {score:.1f}/{games}  → est {est}")
            out.write_text(json.dumps(rows, indent=2))
    finally:
        await ref.quit()
        await pool.stop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=4)
    ap.add_argument("--bots", default="")
    ap.add_argument("--out", default="data/bot_calibration.json")
    ap.add_argument("--seed", type=int, default=3)
    a = ap.parse_args()
    asyncio.run(main(a.games, [b for b in a.bots.split(",") if b] or None, Path(a.out), a.seed))
