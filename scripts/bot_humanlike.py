"""Measures how human a bot's moves look: centipawn loss, hung pieces, moves outside the engine's
top 8, free pieces taken, opening habits and how games end. Every bot move is judged at depth 14.
--positions FILE (lichess positions with their game history, one JSON per line: moves, move, band) instead
measures Maia's sampling settings against the human moves, and Maia's blunders against the humans'.
Usage: python -m scripts.bot_humanlike --bots sam,nova,rafa --games 10 [--out stats.json] | --positions FILE"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
from collections import Counter
from pathlib import Path

import chess
import chess.engine

from backend.bots import maia
from backend.bots.roster import MaiaProfile, get_bot
from backend.bots.selector import FREE_PIECE_PAWNS, _shape, choose_move
from backend.engine.locator import find_engine_command
from backend.engine.pool import pool
from backend.engine.score import cp_from_score
from backend.review.classify import ACPL_CP_CAP
from backend.review.report import _sacrificed_pawns, exchange_gain

JUDGE_DEPTH = 14
JUDGE_LINES = 8  # a move none of these lines starts with is "outside the top 8"
REFERENCE_ELO = 1320  # Stockfish's lowest UCI_Elo
REFERENCE_MOVETIME_SECONDS = 0.1
MAX_PLIES = 160
HANG_MIN_LOSS_CP = 200  # a piece left en prise counts as hung only when the engine agrees it is lost (a sound sacrifice is not)
PUNISH_MAX_LOSS_CP = 50  # a move this close to the best also counts as punishing
OPENING_OWN_MOVES = 10
MINORS = {chess.WHITE: (chess.B1, chess.G1, chess.C1, chess.F1), chess.BLACK: (chess.B8, chess.G8, chess.C8, chess.F8)}


def _clamp(cp: int) -> int:
    return max(-ACPL_CP_CAP, min(ACPL_CP_CAP, cp))


def _free_piece_squares(board: chess.Board) -> set[chess.Square]:
    """Squares of the opponent's pieces the side to move wins at least a piece on by static exchange."""
    them = not board.turn
    return {sq for sq in chess.SQUARES if board.color_at(sq) == them and exchange_gain(board, sq) >= FREE_PIECE_PAWNS}


async def judge(judge_engine: chess.engine.Protocol, board: chess.Board, move: chess.Move, source: str) -> dict:
    limit = chess.engine.Limit(depth=JUDGE_DEPTH)
    infos = await judge_engine.analyse(board, limit, multipv=min(JUDGE_LINES, board.legal_moves.count()))
    best_cp = _clamp(cp_from_score(infos[0]["score"], board.turn))
    top = [i["pv"][0] for i in infos if i.get("pv")]
    free = _free_piece_squares(board)
    after = board.copy()
    after.push(move)
    if after.is_game_over():
        after_cp = ACPL_CP_CAP if after.is_checkmate() else 0
    else:
        after_cp = -_clamp(cp_from_score((await judge_engine.analyse(after, limit))["score"], after.turn))
    loss = max(0, best_cp - after_cp)
    offered = bool(free) and top[0].to_square in free  # taking the piece is the engine's own choice
    return {
        "ply": board.ply(), "source": source, "cp_loss": loss,
        "outside_top": move not in top,
        "hang": loss >= HANG_MIN_LOSS_CP and _sacrificed_pawns(board, move) >= FREE_PIECE_PAWNS,
        "offered": offered,
        "punished": offered and (move.to_square in free or loss <= PUNISH_MAX_LOSS_CP),
    }


def opening_habits(moves: list[chess.Move], color: chess.Color) -> dict:
    """One side's opening from move 1: minors developed after 10 moves, castled within 20, queen and rim-pawn moves in the first 10."""
    board = chess.Board()
    own = queen_moves = rim_pawns = 0
    castled = False
    developed = None
    for mv in moves:
        if board.turn == color:
            own += 1
            piece = board.piece_type_at(mv.from_square)
            if own <= OPENING_OWN_MOVES:
                queen_moves += piece == chess.QUEEN
                rim_pawns += piece == chess.PAWN and chess.square_file(mv.from_square) in (0, 7)
            castled = castled or (own <= 2 * OPENING_OWN_MOVES and board.is_castling(mv))
        board.push(mv)
        if own == OPENING_OWN_MOVES and developed is None:
            developed = sum(1 for sq in MINORS[color] if board.color_at(sq) != color or board.piece_type_at(sq) not in (chess.KNIGHT, chess.BISHOP))
    return {"developed": developed, "castled": castled, "queen_moves": queen_moves, "rim_pawns": rim_pawns}


def ending(board: chess.Board) -> str:
    outcome = board.outcome(claim_draw=True)
    return outcome.termination.name.lower() if outcome else "move cap"


async def play(bot_id: str, judge_engine, ref, vs_ref: bool, bot_white: bool, rng: random.Random) -> tuple[list[dict], dict]:
    bot = get_bot(bot_id)
    board = chess.Board()
    judged: list[dict] = []
    while not board.is_game_over(claim_draw=True) and len(board.move_stack) < MAX_PLIES:
        if vs_ref and board.turn != bot_white:
            board.push((await ref.play(board, chess.engine.Limit(time=REFERENCE_MOVETIME_SECONDS))).move)
            continue
        choice = await choose_move(board, bot, pool, rng)
        judged.append(await judge(judge_engine, board, choice.move, choice.source))
        board.push(choice.move)
    sides = [chess.WHITE if bot_white else chess.BLACK] if vs_ref else [chess.WHITE, chess.BLACK]
    result = board.result(claim_draw=True)
    score = 0.5 if result in ("1/2-1/2", "*") else float((result == "1-0") == bot_white)
    game = {"vs": "reference" if vs_ref else "self", "plies": len(board.move_stack), "ending": ending(board),
            "score": score if vs_ref else None, "opening": [opening_habits(board.move_stack, c) for c in sides]}
    return judged, game


SAMPLINGS = [("argmax", MaiaProfile(0, 0.0))] + [(f"T={t}", MaiaProfile(0, t)) for t in (0.3, 0.5, 0.7, 1.0)]     + [(f"top-p={p}", MaiaProfile(0, 1.0, p)) for p in (0.5, 0.7, 0.9)]     + [(f"T={t},p={p}", MaiaProfile(0, t, p)) for t in (0.5, 0.7) for p in (0.7, 0.9)]
BLUNDER_CP = 300  # a move losing this much against the best (depth RAIL_DEPTH) is a blunder
RAIL_DEPTH = 12
RAIL_POSITIONS = 200  # per band: the blunder comparison is engine work, the sampling table is not


async def positions_report(path: Path, seed: int) -> None:
    """Per band: top-1 match and variety of each sampling (exact, from the distribution), then the share of
    blunders and missed mates in one for the human and for the band's ladder profile."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    bands = sorted({r["band"] for r in rows})
    print("| band | setting | top-1 match % | runs differ % | distinct moves / 5 runs |" + "\n|---|---|---|---|---|")
    for band in bands:
        acc = {name: [0.0, 0.0, 0.0] for name, _ in SAMPLINGS}
        for r in (r for r in rows if r["band"] == band):
            board = chess.Board()
            for m in r["moves"]:
                board.push_uci(m)
            probs = maia.policy(board, band, band)
            for name, prof in SAMPLINGS:
                q = _shape(probs, prof)
                acc[name][0] += q.get(chess.Move.from_uci(r["move"]), 0.0)
                acc[name][1] += 1 - sum(x * x for x in q.values())  # two seeded runs differ
                acc[name][2] += sum(1 - (1 - x) ** 5 for x in q.values())  # expected distinct moves in 5 runs
        n = sum(r["band"] == band for r in rows)
        for name, _ in SAMPLINGS:
            a = acc[name]
            print(f"| {band} | {name} | {100 * a[0] / n:.1f} | {100 * a[1] / n:.1f} | {a[2] / n:.2f} |", flush=True)
    _, engine = await chess.engine.popen_uci(find_engine_command())
    rng = random.Random(seed)
    print("\n| band | profile | positions | human blunders % | Maia blunders % | mate in 1 missed: human / Maia |" + "\n|---|---|---|---|---|---|")
    try:
        for band in bands:
            bot = min((get_bot(b) for b in ("sam", "nova", "mei", "ivy", "zara")), key=lambda b: abs(b.elo - band))
            prof = MaiaProfile(band, bot.maia.temperature, bot.maia.top_p)
            blunders = {"human": 0, "maia": 0}
            mates = {"human": 0, "maia": 0}
            band_rows = [r for r in rows if r["band"] == band][:RAIL_POSITIONS]
            for r in band_rows:
                board = chess.Board()
                for m in r["moves"]:
                    board.push_uci(m)
                shaped = _shape(maia.policy(board, band, band), prof)
                picks = {"human": chess.Move.from_uci(r["move"]), "maia": rng.choices(list(shaped), list(shaped.values()))[0]}
                best = (await engine.analyse(board, chess.engine.Limit(depth=RAIL_DEPTH)))["score"]
                best_cp = _clamp(cp_from_score(best, board.turn))
                for who, mv in picks.items():
                    after = board.copy()
                    after.push(mv)
                    if after.is_checkmate():
                        continue
                    if best.pov(board.turn).mate() == 1:
                        mates[who] += 1
                    got = 0 if after.is_game_over() else -cp_from_score(
                        (await engine.analyse(after, chess.engine.Limit(depth=RAIL_DEPTH)))["score"], after.turn)
                    blunders[who] += best_cp - _clamp(got) >= BLUNDER_CP
            n = len(band_rows)
            print(f"| {band} | T={prof.temperature},p={prof.top_p} | {n} | {100 * blunders['human'] / n:.1f} | "
                  f"{100 * blunders['maia'] / n:.1f} | {mates['human']} / {mates['maia']} |", flush=True)
    finally:
        await engine.quit()


def summary(moves: list[dict], games: list[dict]) -> dict:
    loss = sorted(m["cp_loss"] for m in moves)
    offered = [m for m in moves if m["offered"]]
    opening = [o for g in games for o in g["opening"]]
    developed = [o["developed"] for o in opening if o["developed"] is not None]

    def pct(n: int, d: int) -> float | None:
        return round(100 * n / d, 1) if d else None

    return {
        "moves": len(moves), "acpl": round(statistics.mean(loss), 1),
        "cp_loss_p50": loss[len(loss) // 2], "cp_loss_p90": loss[int(len(loss) * 0.9)],
        "loss_0_49": pct(sum(x < 50 for x in loss), len(loss)), "loss_50_99": pct(sum(50 <= x < 100 for x in loss), len(loss)),
        "loss_100_299": pct(sum(100 <= x < 300 for x in loss), len(loss)), "loss_300_plus": pct(sum(x >= 300 for x in loss), len(loss)),
        "hang_pct": pct(sum(m["hang"] for m in moves), len(moves)),
        "random_pct": pct(sum(m["source"] == "random" for m in moves), len(moves)),
        "slip_pct": pct(sum(m["source"] == "slip" for m in moves), len(moves)),
        "outside_top8_pct": pct(sum(m["outside_top"] for m in moves), len(moves)),
        "free_piece_offers": len(offered), "punish_pct": pct(sum(m["punished"] for m in offered), len(offered)),
        "developed_by_move10": round(statistics.mean(developed), 2) if developed else None,
        "castled_pct": pct(sum(o["castled"] for o in opening), len(opening)),
        "queen_moves_first10": round(statistics.mean(o["queen_moves"] for o in opening), 2),
        "rim_pawns_first10": round(statistics.mean(o["rim_pawns"] for o in opening), 2),
        "score_vs_reference": sum(g["score"] for g in games if g["vs"] == "reference"),
        "endings": dict(Counter(f'{g["vs"]}:{g["ending"]}' for g in games)),
        "mean_plies": round(statistics.mean(g["plies"] for g in games)),
    }


async def main(bot_ids: list[str], games: int, out: Path | None, seed: int) -> None:
    await pool.start()
    _, judge_engine = await chess.engine.popen_uci(find_engine_command())
    _, ref = await chess.engine.popen_uci(find_engine_command())
    await ref.configure({"UCI_LimitStrength": True, "UCI_Elo": REFERENCE_ELO})
    rng = random.Random(seed)
    stats = {}
    try:
        for bot_id in bot_ids:
            moves, played = [], []
            for vs_ref in (True, False):
                for g in range(games):
                    judged, game = await play(bot_id, judge_engine, ref, vs_ref, g % 2 == 0, rng)
                    moves += judged
                    played.append(game)
            stats[bot_id] = summary(moves, played)
            print(bot_id, json.dumps(stats[bot_id]), flush=True)
    finally:
        await judge_engine.quit()
        await ref.quit()
        await pool.stop()
    if out:
        out.write_text(json.dumps(stats, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bots", default="sam,nova,rafa")
    ap.add_argument("--games", type=int, default=10)
    ap.add_argument("--out", default="")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--positions", default="")
    a = ap.parse_args()
    if a.positions:
        raise SystemExit(asyncio.run(positions_report(Path(a.positions), a.seed)))
    asyncio.run(main(a.bots.split(","), a.games, Path(a.out) if a.out else None, a.seed))
