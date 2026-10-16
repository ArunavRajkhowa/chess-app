"""Checks lesson JSON before it ships: schema and legality (the same rules the loader applies) and,
with --engine, that every challenge solution is the engine's best move or a fastest mate and every
drill is achievable. Exit 1 on any finding. Usage: python -m scripts.validate_lessons data/lessons/x.json [--engine]"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import chess

from backend.content.lessons import SECTION_TYPES, _validate_section  # noqa: F401 (schema rules live there)
from backend.engine.pool import EnginePool
from backend.engine.score import cp_from_score

CHALLENGE_DEPTH = 16
MAX_GAP_CP = 60


def structural(path: Path) -> tuple[list[dict], list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    findings: list[str] = []
    sections_ok: list[dict] = []
    modules = data.get("modules", [data] if "lessons" in data else [])
    ids: set[str] = set()
    for m in modules:
        for key in ("id", "band", "title", "lessons"):
            if key not in m:
                findings.append(f"module {m.get('id', '?')}: missing {key}")
        for lsn in m.get("lessons", []):
            if lsn.get("id") in ids:
                findings.append(f"duplicate lesson id {lsn.get('id')}")
            ids.add(lsn.get("id"))
            if not lsn.get("sections"):
                findings.append(f"lesson {lsn.get('id')}: no sections")
            for i, sec in enumerate(lsn.get("sections", [])):
                try:
                    s = _validate_section(dict(sec))
                    s["_lesson"] = lsn.get("id")
                    s["_index"] = i
                    sections_ok.append(s)
                except (ValueError, KeyError) as exc:
                    findings.append(f"lesson {lsn.get('id')} section {i} ({sec.get('type')}): {exc}")
    return sections_ok, findings


async def engine_checks(sections: list[dict]) -> list[str]:
    findings: list[str] = []
    pool = EnginePool()
    await pool.start()
    try:
        for s in sections:
            tag = f"lesson {s['_lesson']} section {s['_index']}"
            if s["type"] == "challenge" and not s.get("accept_any_legal") and not s.get("accept_any_check"):
                board = chess.Board(s["fen"])
                infos = await pool.analyse(board, depth=CHALLENGE_DEPTH, multipv=2)
                best = infos[0]["pv"][0]
                sol = chess.Move.from_uci(s["solution"][0])
                if best != sol:
                    b2 = board.copy()
                    b2.push(sol)
                    sol_info = await pool.analyse(b2, depth=CHALLENGE_DEPTH)
                    best_cp = cp_from_score(infos[0]["score"], board.turn)
                    sol_cp = -cp_from_score(sol_info[0]["score"], b2.turn) if not b2.is_game_over() else (10000 if b2.is_checkmate() else 0)
                    if best_cp - sol_cp > MAX_GAP_CP:
                        findings.append(f"{tag}: solution {board.san(sol)} is not best; engine prefers {board.san(best)} (gap {best_cp - sol_cp} cp)")
                # the opponent's replies in the solution should be the engine's choice (or at least not blunders)
                b = board.copy()
                for i, uci in enumerate(s["solution"]):
                    mv = chess.Move.from_uci(uci)
                    if i % 2 == 1 and not b.is_game_over():
                        inf = await pool.analyse(b, depth=12, multipv=1)
                        if inf and inf[0]["pv"][0] != mv:
                            findings.append(f"{tag}: opponent reply {b.san(mv)} is not the engine's defence ({b.san(inf[0]['pv'][0])}); the solver's line may have a cook")
                    b.push(mv)
            elif s["type"] == "drill":
                board = chess.Board(s["fen"])
                infos = await pool.analyse(board, depth=14)
                cp = cp_from_score(infos[0]["score"], board.turn) if infos else 0
                goal = s["goal"]
                if goal in ("mate", "win_material", "promote") and cp < 300:
                    findings.append(f"{tag}: drill goal {goal} but the position is only {cp:+d} cp for the learner")
                if goal in ("draw", "survive") and cp < -200:
                    findings.append(f"{tag}: drill goal {goal} but the learner is lost ({cp:+d} cp)")
    finally:
        await pool.stop()
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--engine", action="store_true")
    a = ap.parse_args()
    total = 0
    for f in a.files:
        path = Path(f)
        sections, findings = structural(path)
        if a.engine:
            findings += asyncio.run(engine_checks(sections))
        kinds = {}
        for s in sections:
            kinds[s["type"]] = kinds.get(s["type"], 0) + 1
        print(f"{path.name}: {len(sections)} valid sections {kinds}; {len(findings)} finding(s)")
        for x in findings:
            print("  -", x)
        total += len(findings)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
