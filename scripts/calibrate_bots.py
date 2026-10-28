"""Measures each bot's strength by playing it against Stockfish limited to a fixed Elo
(UCI_LimitStrength) and estimating a performance rating from the score. A specialist plays from its
own start; each pair of games shares one start with colours swapped. Merges rows into
data/bot_calibration.json by bot id. --elo-self tries a Maia rating on the listed bots; --pairs plays
bots against each other (a label under Stockfish's floor of 1320 is checked against its ladder neighbours).
Usage: python -m scripts.calibrate_bots --games 4 [--bots pip,endgame-rook-1400] [--elo-self 900] [--pairs luna:sam]"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
from dataclasses import replace
from pathlib import Path

import chess
import chess.engine

from backend.bots.roster import Bot, get_bot
from backend.bots.selector import _material_balance, choose_move
from backend.bots.specialists import all_bots
from backend.engine.locator import find_engine_command
from backend.engine.pool import pool
from backend.routers.play import specialist_start

REFERENCE_MOVETIME_SECONDS = 0.1
MIN_UCI_ELO, MAX_UCI_ELO = 1320, 3190
MAX_PLIES = 160
ADJUDICATE_PAWNS = 3  # a game still going at MAX_PLIES goes to the side this much material ahead, else it is drawn


async def play_game(ref: chess.engine.Protocol | None, bot: Bot, bot_is_white: bool, rng: random.Random, start_fen: str | None,
                    other: Bot | None = None) -> float:
    """The bot's score in one game against the reference engine, or against the other bot when given."""
    board = chess.Board(start_fen) if start_fen else chess.Board()
    while not board.is_game_over(claim_draw=True) and len(board.move_stack) < MAX_PLIES:
        if board.turn == (chess.WHITE if bot_is_white else chess.BLACK):
            choice = await choose_move(board, bot, pool, rng)
            board.push(choice.move)
        elif other is not None:
            board.push((await choose_move(board, other, pool, rng)).move)
        else:
            res = await ref.play(board, chess.engine.Limit(time=REFERENCE_MOVETIME_SECONDS))
            board.push(res.move)
    result = board.result(claim_draw=True)
    if result == "*":
        edge = _material_balance(board, chess.WHITE if bot_is_white else chess.BLACK)
        return 0.5 if abs(edge) < ADJUDICATE_PAWNS else float(edge > 0)
    if result == "1/2-1/2":
        return 0.5
    return 1.0 if (result == "1-0") == bot_is_white else 0.0


def performance(ref_elo: int, score: float, n: int) -> int:
    p = min(max(score / n, 0.02), 0.98)
    return int(round(ref_elo + 400 * math.log10(p / (1 - p))))


def _key(row: dict) -> str:
    return f'{row["bot"]}:{row["opponent"]}' if "opponent" in row else row["bot"]


def _with_elo_self(bot: Bot, elo_self: int | None) -> Bot:
    if elo_self is None:
        return bot
    if bot.maia is None:
        raise SystemExit(f"--elo-self {elo_self}: bot {bot.id!r} has no Maia profile; expected a Maia bot")
    return replace(bot, maia=replace(bot.maia, elo_self=elo_self))


async def main(games: int, only: list[str] | None, out: Path, seed: int, elo_self: int | None, pairs: list[str]) -> None:
    await pool.start()
    _, ref = await chess.engine.popen_uci(find_engine_command())
    rng = random.Random(seed)
    random.seed(seed)  # specialist_start shuffles with the module's generator
    rows: dict[str, dict] = {_key(r): r for r in json.loads(out.read_text())} if out.exists() else {}
    try:
        for pair in pairs:
            a, b = (get_bot(x) for x in pair.split(":"))
            score = 0.0
            for g in range(games):
                score += await play_game(None, a, bot_is_white=(g % 2 == 0), rng=rng, start_fen=None, other=b)
            row = {"bot": a.id, "opponent": b.id, "label_elo": a.elo, "opponent_elo": b.elo, "games": games, "score": score}
            rows[_key(row)] = row
            print(f"{a.id} ({a.elo}) vs {b.id} ({b.elo}): {score:.1f}/{games}", flush=True)
            out.write_text(json.dumps(list(rows.values()), indent=2))
        for bot in all_bots():
            if only is None and pairs or only and bot.id not in only:
                continue
            bot = _with_elo_self(bot, elo_self)
            ref_elo = min(max(bot.elo, MIN_UCI_ELO), MAX_UCI_ELO)
            await ref.configure({"UCI_LimitStrength": True, "UCI_Elo": ref_elo})
            score = 0.0
            start_fen = None
            for g in range(games):
                if g % 2 == 0 and bot.specialty and bot.specialty.start_fens:
                    start_fen = await specialist_start(bot, "white")  # an endgame's task is White's
                score += await play_game(ref, bot, bot_is_white=(g % 2 == 0), rng=rng, start_fen=start_fen)
            est = performance(ref_elo, score, games)
            rows[bot.id] = {"bot": bot.id, "label_elo": bot.elo, "reference_elo": ref_elo, "games": games, "score": score, "estimated_elo": est}
            if bot.maia:
                rows[bot.id]["maia_elo_self"] = bot.maia.elo_self
            print(f"{bot.id:32s} label {bot.elo:5d}  vs SF@{ref_elo}: {score:.1f}/{games}  -> est {est}", flush=True)
            out.write_text(json.dumps(list(rows.values()), indent=2))
    finally:
        await ref.quit()
        await pool.stop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=4)
    ap.add_argument("--bots", default="")
    ap.add_argument("--out", default="data/bot_calibration.json")
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--elo-self", type=int, default=None)
    ap.add_argument("--pairs", default="")
    a = ap.parse_args()
    asyncio.run(main(a.games, [b for b in a.bots.split(",") if b] or None, Path(a.out), a.seed, a.elo_self,
                     [p for p in a.pairs.split(",") if p]))
