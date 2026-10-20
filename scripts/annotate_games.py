"""Precomputes the study annotation of every master game and lesson model game into data/study/, with
several engines in parallel. Skips games already cached. Usage: python -m scripts.annotate_games [--workers 4]"""
from __future__ import annotations

import argparse
import asyncio
import io
import sys
import time

import chess
import chess.pgn

from backend.content.games import load_games
from backend.content.lessons import load_curriculum
from backend.engine.pool import EnginePool
from backend.study.annotate import _store, annotate, cached, study_key


def jobs() -> list[tuple[str, str, list[chess.Move]]]:
    out = []
    for g in load_games():
        out.append((f"game {g.id}", chess.STARTING_FEN, [chess.Move.from_uci(p["uci"]) for p in g.plies]))
    for m in load_curriculum():
        for lsn in m.lessons:
            for i, sec in enumerate(lsn.sections):
                if sec["type"] == "game":
                    game = chess.pgn.read_game(io.StringIO(sec["pgn"]))
                    out.append((f"lesson {lsn.id}#{i}", sec["start_fen"], list(game.mainline_moves()) if game else []))
    return [(name, fen, moves) for name, fen, moves in out if moves and not cached(study_key(fen, [m.uci() for m in moves]))]


async def worker(queue: asyncio.Queue, n: int) -> None:
    pool = EnginePool()
    await pool.start()
    try:
        while not queue.empty():
            name, fen, moves = await queue.get()
            t = time.perf_counter()
            try:
                doc = await annotate(moves, pool, start_fen=fen)
                _store(study_key(fen, [m.uci() for m in moves]), doc)
                print(f"[{n}] {name}: {len(moves)} plies in {time.perf_counter() - t:.0f}s", flush=True)
            except Exception as exc:  # boundary: one bad game must not stop the batch
                print(f"[{n}] {name}: FAILED {type(exc).__name__}: {exc}", flush=True)
    finally:
        await pool.stop()


async def main(workers: int) -> None:
    todo = jobs()
    print(f"{len(todo)} games to annotate with {workers} engines", flush=True)
    queue: asyncio.Queue = asyncio.Queue()
    for j in todo:
        queue.put_nowait(j)
    await asyncio.gather(*(worker(queue, n) for n in range(workers)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    asyncio.run(main(a.workers))
    sys.exit(0)
