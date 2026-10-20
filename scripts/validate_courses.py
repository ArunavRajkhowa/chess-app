"""Checks opening-course JSON before it ships: every line and trap loads under the loader's rules and,
with --engine, every trap's mistake loses at least a mistake's worth of win chance, its punishment is
the engine's move, and no main-line move is a mistake. Exit 1 on any finding."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import chess

from backend.engine.pool import EnginePool
from backend.engine.score import cp_from_score, win_percent_from_cp
from backend.openings.courses import CourseLine, _line, parse_course
from backend.review.classify import EXCELLENT_MAX_DROP, INACCURACY_MAX_DROP

DEPTH = 18


def structural(path: Path) -> tuple[list[CourseLine], list[CourseLine], list[str]]:
    try:
        parse_course(path, [])
    except (ValueError, json.JSONDecodeError) as exc:
        return [], [], [f"{path.name}: {exc}"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    found: dict[bool, list[CourseLine]] = {False: [], True: []}
    findings: list[str] = []
    for key, trap in (("lines", False), ("traps", True)):
        for r in raw[key]:
            try:
                found[trap].append(_line(r, raw["openings"], trap=trap))
            except ValueError as exc:
                findings.append(f"{path.name} {key} {r.get('id')}: {exc}")
    return found[False], found[True], findings


class Judge:
    """Win chance and best move per position, each position analysed once."""

    def __init__(self, pool: EnginePool) -> None:
        self.pool = pool
        self.seen: dict[str, tuple[float, chess.Move | None]] = {}

    async def at(self, fen: str) -> tuple[float, chess.Move | None]:
        if fen not in self.seen:
            board = chess.Board(fen)
            if board.is_checkmate():
                self.seen[fen] = (0.0 if board.turn == chess.WHITE else 100.0, None)
            elif board.is_game_over():
                self.seen[fen] = (50.0, None)
            else:
                info = (await self.pool.analyse(board, depth=DEPTH))[0]
                self.seen[fen] = (win_percent_from_cp(cp_from_score(info["score"], chess.WHITE)), info["pv"][0])
        return self.seen[fen]

    async def drop(self, x: CourseLine, ply: int) -> tuple[float, float, float, bool]:
        """The mover's win% before and after ply `ply`, the drop, and whether it was the engine's move."""
        before = chess.STARTING_FEN if ply == 1 else x.plies[ply - 2]["fen"]
        white = chess.Board(before).turn == chess.WHITE
        (wb, best), (wa, _) = await self.at(before), await self.at(x.plies[ply - 1]["fen"])
        wb, wa = (wb, wa) if white else (100 - wb, 100 - wa)
        return wb, wa, wb - wa, best is not None and best.uci() == x.plies[ply - 1]["uci"]


def _label(x: CourseLine, ply: int) -> str:
    return f"{(ply + 1) // 2}{'.' if ply % 2 else '...'}{x.plies[ply - 1]['san']}"


async def engine_checks(lines: list[CourseLine], traps: list[CourseLine], judge: Judge, name: str) -> list[str]:
    findings: list[str] = []
    for x in lines:
        drops = [(await judge.drop(x, p))[2] for p in range(1, len(x.plies) + 1)]
        worst = max(range(len(drops)), key=drops.__getitem__) + 1
        print(f"  line {x.id}: worst move {_label(x, worst)} loses {drops[worst - 1]:.1f}")
        findings += [f"{name} line {x.id}: {_label(x, p)} loses {d:.1f} win%, a mistake" for p, d in enumerate(drops, 1) if d > INACCURACY_MAX_DROP]
    for x in traps:
        m = x.mistake_ply
        wb, wa, d, _ = await judge.drop(x, m)
        print(f"  trap {x.id}: mistake {_label(x, m)} loses {d:.1f} ({wb:.1f} -> {wa:.1f})", end="")
        if d <= INACCURACY_MAX_DROP:
            findings.append(f"{name} trap {x.id}: mistake {_label(x, m)} loses only {d:.1f} win%, expected more than {INACCURACY_MAX_DROP}")
        if m >= len(x.plies):
            print()
            findings.append(f"{name} trap {x.id}: no punishment move after {_label(x, m)}")
            continue
        _, _, pd, is_best = await judge.drop(x, m + 1)
        print(f"; punishment {_label(x, m + 1)} {'is the engine move' if is_best else f'loses {pd:.1f}'}")
        if not is_best and pd > EXCELLENT_MAX_DROP:
            findings.append(f"{name} trap {x.id}: punishment {_label(x, m + 1)} loses {pd:.1f} win%, expected the engine move or within {EXCELLENT_MAX_DROP}")
    return findings


async def run(paths: list[Path], engine: bool) -> int:
    pool = EnginePool()
    if engine:
        await pool.start()
    total = 0
    try:
        judge = Judge(pool)
        for path in paths:
            lines, traps, findings = structural(path)
            print(f"{path.name}: {len(lines)} lines, {len(traps)} traps")
            if engine:
                findings += await engine_checks(lines, traps, judge, path.name)
            for f in findings:
                print("  -", f)
            total += len(findings)
    finally:
        if engine:
            await pool.stop()
    print(f"{total} finding(s)")
    return 1 if total else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--engine", action="store_true")
    a = ap.parse_args()
    return asyncio.run(run([Path(f) for f in a.files], a.engine))


if __name__ == "__main__":
    sys.exit(main())
