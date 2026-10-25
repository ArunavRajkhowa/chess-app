"""Scores the coach's answers: for each position, the facts a good answer must mention, and any move
it names that is legal nowhere in the facts. Runs the rule-based fallback always, the model when .env sets one.
Usage: python -m scripts.coach_eval [--model] [--limit N] [--only LABEL]"""
from __future__ import annotations

import argparse
import asyncio
import re
import time
from dataclasses import dataclass, field

import chess

from backend.coach import client
from backend.engine.pool import pool
from backend.puzzles.store import load_library
from backend.routers.coach import _unverified_moves, chat_answer
from backend.storage.db import database

QUESTION = "What is going on here, and what should I do?"
EVAL_NUMBER = re.compile(r"[+-]\d+\.\d\d|-?M\d")
ASKS_BACK = re.compile(r"\?\s*$")
BEHIND = r"pawns? down|behind|White is \d+ pawns? (up|ahead)"


@dataclass
class Case:
    id: str
    labels: list[str]  # opening/middlegame/endgame, winning/losing, after-blunder, beginner/advanced
    fen: str
    level: str
    must: dict[str, str]  # what a good answer names -> regex that finds it
    last_move: str | None = None  # UCI, played from `previous_fen`
    previous_fen: str | None = None
    game: dict = field(default_factory=dict)  # extra game context: earlier mistakes


CURATED = [
    Case("italian", ["opening", "beginner"], "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3", "beginner",
         {"names the Italian Game": r"Italian", "a book developing move (Bc5 or Nf6)": r"\b(Bc5|Nf6)\b", "the development goal": r"develop|castle"}),
    Case("scholar-threat", ["opening", "beginner"], "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3", "beginner",
         {"names the threat Qxf7#": r"Qxf7", "a move that stops it": r"\b(g6|Qe7|Qf6|Nh6)\b", "says it is mate": r"mate"},
         last_move="d1h5", previous_fen="r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/8/PPPP1PPP/RNBQK1NR w KQkq - 2 3"),
    Case("ruy-open", ["opening", "advanced"], "r1bqkb1r/1ppp1ppp/p1n2n2/4p3/B3P3/5N2/PPPP1PPP/RNBQ1RK1 b kq - 5 5", "advanced",
         {"names the Ruy Lopez": r"Ruy Lopez", "a main-line move (Be7, Nxe4 or b5)": r"\b(Be7|Nxe4|b5)\b", "an evaluation": EVAL_NUMBER.pattern}),
    Case("qgd", ["opening", "intermediate"], "rnbqkbnr/ppp2ppp/4p3/3p4/2PP4/8/PP2PPPP/RNBQKBNR w KQkq - 0 3", "intermediate",
         {"names the Queen's Gambit Declined": r"Queen's Gambit Declined", "a main-line move (Nc3, Nf3, cxd5)": r"\b(Nc3|Nf3|cxd5)\b"}),
    Case("qh4-blunder", ["opening", "after-blunder", "winning", "beginner"], "rnb1kbnr/pppp1ppp/8/4p3/4P2q/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3", "beginner",
         {"names Nxh4": r"Nxh4", "says the queen is lost": r"queen", "names the blunder Qh4": r"Qh4"},
         last_move="d8h4", previous_fen="rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"),
    Case("najdorf", ["middlegame", "advanced"], "r2q1rk1/3nbppp/p2pbn2/4p1P1/1p2P3/1NN1BP2/PPPQ3P/2KR1B1R w - - 0 13", "advanced",
         {"names the threat bxc3": r"bxc3", "a knight move that saves it (Na4 or Ne2)": r"\b(Na4|Ne2)\b", "names the attacked knight": r"knight on c3|c3"},
         last_move="b5b4", previous_fen="r2q1rk1/3nbppp/p2pbn2/1p2p1P1/4P3/1NN1BP2/PPPQ3P/2KR1B1R b - - 0 12"),
    Case("iqp", ["middlegame", "intermediate"], "r1bq1rk1/pp2bppp/2n1pn2/8/3P4/2NB1N2/PP3PPP/R1BQ1RK1 w - - 0 10", "intermediate",
         {"names the isolated pawn": r"isolated", "on d4": r"d4", "the plan for its owner (attack, half-open files)": r"attack|half-open|space"}),
    Case("open-files", ["middlegame", "advanced"], "r2q1rk1/pp2bppp/2n1bn2/8/8/2N1BN2/PP2BPPP/R2Q1RK1 w - - 0 10", "advanced",
         {"names an open file": r"[cde]-file", "a rook belongs there": r"rook|R[acdf]?[cde]1"}),
    Case("piece-down", ["middlegame", "losing", "intermediate"], "r1bqk2r/pppp1ppp/2n5/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R b KQkq - 0 5", "intermediate",
         {"says White is better": r"White is (winning|clearly better|\d+ pawns? (up|ahead))", "the losing side's plan (keep pieces, make threats, counterplay)": r"keep pieces|complicat|counterplay|make threats"}),
    Case("rook-up", ["middlegame", "winning", "intermediate"], "r1bqk3/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQq - 0 5", "intermediate",
         {"says White is winning": r"White is (winning|\d+ pawns? (up|ahead))", "the winning side's plan (trade, simplify)": r"trade|simplif"}),
    Case("kp-endgame", ["endgame", "winning", "intermediate"], "8/8/4k3/8/3K4/3P4/8/8 w - - 0 1", "intermediate",
         {"the pawn-endgame rule (opposition, king in front)": r"opposition|king in front", "the king move (Kc5 or Ke4)": r"\bK(c5|e4)\b"}),
    Case("lucena", ["endgame", "winning", "advanced"], "1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1", "advanced",
         {"the rook-endgame rule (Lucena, bridge, cut the king off)": r"Lucena|bridge|cut", "a winning rook move": r"\bR[a-h][1-8]\+?"}),
    Case("own-blunder", ["middlegame", "after-blunder", "losing", "intermediate"],
         "r3qrk1/ppp5/2nppn2/2b1p1p1/4P2B/2PP4/PP1NQPPP/R4RK1 w - - 0 13", "intermediate",
         {"points back to the earlier blunder Nxg5": r"Nxg5", "says when (move 12)": r"move 12|earlier", "names the last move hxg5": r"hxg5"},
         last_move="h6g5", previous_fen="r3qrk1/ppp5/2nppn1p/2b1p1N1/4P2B/2PP4/PP1NQPPP/R4RK1 b - - 0 12",
         game={"earlier_mistakes": [{"move_number": 12, "san": "Nxg5", "classification": "blunder", "best": "Bg3"}],
               "positions": ["r3qrk1/ppp5/2nppn1p/2b1p1p1/4P2B/2PP1N2/PP1NQPPP/R4RK1 w - - 0 12"],
               "played": ["Nxg5"]}),  # the app's context lists every move played; the case needs only this one
    # Losing on material, drawn by the engine: the answer must find the drawing resource.
    Case("perpetual", ["endgame", "losing", "intermediate"], "6k1/R4ppp/R7/1P6/P7/7P/5PPK/2q5 b - - 0 1", "intermediate",
         {"names perpetual check": r"perpetual", "the checking move Qf4+": r"Qf4", "says Black is behind in material": BEHIND}),
    Case("stalemate-rook", ["endgame", "losing", "advanced"], "7k/5Q2/6KP/8/8/8/8/r7 b - - 0 1", "advanced",
         {"names stalemate": r"stalemate", "a rook check (Rg1+ or Ra6+)": r"\bR(g1|a6)\b", "says Black is behind in material": BEHIND}),
    Case("wrong-bishop", ["endgame", "losing", "intermediate"], "8/5k2/8/8/4K2P/3B4/8/8 b - - 0 1", "intermediate",
         {"names the fortress": r"fortress|wrong.colou?red bishop", "says it is a draw": r"draw", "a king move towards h8": r"\bK(f6|g6|g7|g8)\b"}),
    Case("opposite-bishops", ["endgame", "losing", "advanced"], "8/4k3/8/3KP3/2B5/8/5b2/8 b - - 0 1", "advanced",
         {"names opposite-coloured bishops": r"opposite", "says it is a draw": r"draw", "a bishop move": r"\bB[a-h][1-8]\b"}),
]

# One puzzle per motif: the solver's move, the opponent's move before it, and the motif's own word.
MOTIFS = {
    "fork": r"fork", "pin": r"\bpin", "hangingPiece": r"for free|hanging|undefended|loose", "discoveredAttack": r"uncover|discover",
    "trappedPiece": r"trapped|no safe square", "skewer": r"skewer|x-ray", "mateIn1": r"mate", "mateIn2": r"mate", "backRankMate": r"mate|back rank",
    "defensiveMove": r"threat|defend|parr", "deflection": r"deflect|overload|lure", "rookEndgame": r"rook endgame|rook behind|cut|Lucena|Philidor",
    "pawnEndgame": r"pawn endgame|opposition|king in front|race", "promotion": r"promot|queen",
}


def puzzle_cases() -> list[Case]:
    lib = load_library()
    out = []
    for i, (theme, motif) in enumerate(MOTIFS.items()):
        p = min((p for p in lib.by_theme.get(theme, []) if "short" in p.themes or "oneMove" in p.themes), key=lambda p: p.id, default=None)
        if p is None:
            continue
        before = chess.Board(p.fen)
        opp = chess.Move.from_uci(p.moves[0])
        board = before.copy()
        opp_san = board.san(opp)
        board.push(opp)
        solution = board.san(chess.Move.from_uci(p.moves[1]))
        level = "beginner" if i % 2 == 0 else "advanced"
        phase = "endgame" if "endgame" in p.themes else "opening" if "opening" in p.themes else "middlegame"
        out.append(Case(f"puzzle-{theme}-{p.id}", [phase, "after-blunder", level, theme], board.fen(), level,
                        {f"the solution {solution}": re.escape(solution.rstrip("+#")), f"the opponent's move {opp_san}": re.escape(opp_san.rstrip("+#")),
                         f"the motif ({theme})": motif},
                        last_move=p.moves[0], previous_fen=p.fen))
    return out


def score(case: Case, text: str, boards: list[chess.Board]) -> dict:
    checks = dict(case.must)
    hits = {name: bool(re.search(rx, text, re.I)) for name, rx in checks.items()}
    hits["asks one question back"] = bool(ASKS_BACK.search(text))
    if case.level == "beginner":
        hits["no evaluation numbers for a beginner"] = not EVAL_NUMBER.search(text)
    return {"hits": hits, "score": sum(hits.values()) / len(hits), "unverified": _unverified_moves(text, boards)}


def context_of(case: Case) -> dict:
    game = {"last_move_uci": case.last_move, "positions": [*case.game.get("positions", []), case.previous_fen, case.fen],
            **{k: v for k, v in case.game.items() if k != "positions"}} if case.last_move else None
    return {"player": {"level": case.level}, "game": game, "lesson": None}


async def model_answer(user: str) -> str:
    return "".join([t async for t in client.stream_text(system=client.prompt("coach_system"), user=user, purpose="eval")])


async def run(use_model: bool, limit: int | None, pause: float, only: str | None = None) -> None:
    cases = [c for c in CURATED + puzzle_cases() if only is None or only in c.labels][:limit]
    await pool.start()
    if use_model:
        await database.start()
    results = {"rules": [], "model": []}
    failures: list[str] = []  # a failed call is named and left out of the mean, never scored as an answer
    try:
        for case in cases:
            board = chess.Board(case.fen)
            user, rules, boards = await chat_answer(board, QUESTION, level=case.level, context=context_of(case))
            r = score(case, rules, boards)
            results["rules"].append((case, r, rules))
            line = f"{case.id:40s} rules {r['score']:.2f}"
            if use_model:
                started = time.monotonic()
                try:
                    text = await model_answer(user)
                    m = score(case, text, boards)
                    results["model"].append((case, m, text))
                    line += f"  model {m['score']:.2f} ({time.monotonic() - started:.0f}s)"
                except Exception as exc:  # boundary: one failed call must not end the run
                    failures.append(f"{case.id}: {exc}")
                    line += "  model FAILED"
                await asyncio.sleep(pause)
            print(line, flush=True)
    finally:
        await pool.stop()
        if use_model:
            await database.stop()
    for source, rows in results.items():
        if not rows:
            continue
        print(f"\n== {source}: {len(rows)} positions")
        print(f"mean score {sum(r['score'] for _, r, _ in rows) / len(rows):.2f}; answers naming an unverified move: {sum(1 for _, r, _ in rows if r['unverified'])}")
        labels = sorted({lbl for c, _, _ in rows for lbl in c.labels if lbl in ("opening", "middlegame", "endgame", "winning", "losing", "after-blunder", "beginner", "advanced")})
        for lbl in labels:
            sel = [r["score"] for c, r, _ in rows if lbl in c.labels]
            print(f"  {lbl:14s} {sum(sel) / len(sel):.2f} over {len(sel)}")
        missed = [f"{c.id}: {name}" for c, r, _ in rows for name, ok in r["hits"].items() if not ok]
        print("missed:\n  " + "\n  ".join(missed) if missed else "missed: none")
        for c, r, _ in rows:
            if r["unverified"]:
                print(f"unverified in {c.id}: {r['unverified']}")
    for f in failures:
        print(f"model call failed (not scored): {f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="store_true", help="also ask the model set in .env")
    ap.add_argument("--limit", type=int, default=None, help="only the first N positions")
    ap.add_argument("--pause", type=float, default=0.0, help="seconds between model calls, for a rate-limited free tier")
    ap.add_argument("--only", default=None, help="only positions with this label, e.g. losing")
    args = ap.parse_args()
    if args.model and not client.llm_enabled():
        print("No coach model is set: fill COACH_BASE_URL and COACH_MODEL in .env (see .env.example).")
        return 1
    asyncio.run(run(args.model, args.limit, args.pause, args.only))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
