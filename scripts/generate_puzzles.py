"""Builds tactics puzzles from PGN games with Stockfish, lichess style: a position where one move
is clearly best, a solution line of only-moves, themes from board heuristics, a rating estimate.
Usage: python -m scripts.generate_puzzles data/games/*.pgn data/selfplay/*.pgn --out data/puzzles/generated.jsonl"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

import chess
import chess.engine
import chess.pgn

from backend.engine.pool import EnginePool
from backend.engine.score import MATE_CP, cp_from_score
from backend.review.phases import ENDGAME, OPENING, phase_of

SCAN_DEPTH = 14
VERIFY_DEPTH = 16
MIN_GAP_CP = 200          # best vs second best for the first solver move
MIN_ONLY_MOVE_GAP = 150   # for later solver moves
MIN_RESULT_CP = 150       # solver must end clearly better
MAX_SOLVER_MOVES = 5
PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


def _mate_distance(score: chess.engine.PovScore, pov: chess.Color) -> int | None:
    s = score.pov(pov)
    return s.mate() if s.is_mate() and (s.mate() or 0) > 0 else None


async def _lines(pool: EnginePool, board: chess.Board, depth: int, multipv: int = 2):
    infos = await pool.analyse(board, depth=depth, multipv=multipv)
    out = []
    for info in infos:
        pv = info.get("pv") or []
        if pv:
            out.append((pv[0], cp_from_score(info["score"], board.turn), info["score"], pv))
    return out


async def extend_solution(pool: EnginePool, board: chess.Board, first: chess.Move) -> list[chess.Move] | None:
    """Solver move, then the opponent's best reply, repeated while the solver has an only-move."""
    solver = board.turn
    b = board.copy()
    moves = [first]
    b.push(first)
    while len(moves) // 2 < MAX_SOLVER_MOVES:
        if b.is_game_over():
            break
        reply = await _lines(pool, b, VERIFY_DEPTH, 1)
        if not reply:
            break
        b.push(reply[0][0])
        moves.append(reply[0][0])
        if b.is_game_over():
            break
        lines = await _lines(pool, b, VERIFY_DEPTH, 2)
        if not lines:
            break
        best_mv, best_cp, best_score, _ = lines[0]
        mate = _mate_distance(best_score, solver)
        gap = best_cp - lines[1][1] if len(lines) > 1 else 9999
        second_mates = len(lines) > 1 and lines[1][2].pov(solver).is_mate() and (lines[1][2].pov(solver).mate() or 0) > 0
        # stop when the tactic has resolved: no only-move left (a second mating move counts as a
        # second solution), or a quiet winning position
        if (gap < MIN_ONLY_MOVE_GAP and mate is None) or (mate is not None and second_mates):
            break
        if mate is None and best_cp < MIN_RESULT_CP:
            return None
        moves.append(best_mv)
        b.push(best_mv)
        if mate == 1 or b.is_checkmate():
            break
    if len(moves) % 2 == 0:
        moves.pop()  # never end on the opponent's reply: the solver's move closes the puzzle
    return moves


def themes_for(board: chess.Board, moves: list[chess.Move], final_cp: int) -> list[str]:
    themes: set[str] = set()
    solver = board.turn
    b = board.copy()
    solver_moves = moves[0::2]
    end = board.copy()
    for mv in moves:
        end.push(mv)
    n_solver = len(solver_moves)
    if end.is_checkmate():
        themes.add("mate")
        themes.add({1: "mateIn1", 2: "mateIn2", 3: "mateIn3"}.get(n_solver, "mateIn4"))
        last = moves[-1]
        piece = end.piece_at(last.to_square)
        ksq = end.king(not solver)
        if ksq is not None and piece:
            krank = chess.square_rank(ksq)
            home = 7 if not solver == chess.WHITE else 0
            if krank == home and piece.piece_type in (chess.ROOK, chess.QUEEN) and chess.square_rank(last.to_square) == home:
                themes.add("backRankMate")
            if piece.piece_type == chess.KNIGHT:
                neighbours = [s for s in chess.SQUARES if chess.square_distance(s, ksq) == 1]
                if all((p := end.piece_at(s)) and p.color == (not solver) for s in neighbours):
                    themes.add("smotheredMate")
    first = moves[0]
    if not b.is_capture(first) and not b.gives_check(first):
        themes.add("quietMove")
    if first.promotion:
        themes.add("promotion")
    mover = b.piece_at(first.from_square)
    if mover and mover.piece_type == chess.PAWN and chess.square_rank(first.to_square) in (1, 6):
        themes.add("advancedPawn")
    if b.is_capture(first):
        victim = b.piece_at(first.to_square)
        if victim and not b.attackers(not solver, first.to_square):
            themes.add("hangingPiece")
    # sacrifice: the solver's piece can be captured by a cheaper piece after the first move
    b2 = b.copy()
    b2.push(first)
    if mover and mover.piece_type != chess.PAWN:
        atk = b2.attackers(not solver, first.to_square)
        if atk and min(PIECE_VALUES[b2.piece_at(a).piece_type] for a in atk) < PIECE_VALUES[mover.piece_type if not first.promotion else first.promotion]:
            themes.add("sacrifice")
    # fork / pin / skewer / discovered attack / double check after each solver move
    bb = board.copy()
    for i, mv in enumerate(moves):
        is_solver = i % 2 == 0
        if is_solver:
            moved = bb.piece_at(mv.from_square)
            before_attackers = {sq: set(bb.attackers(solver, sq)) for sq in bb.pieces(chess.QUEEN, not solver) | bb.pieces(chess.ROOK, not solver) | bb.pieces(chess.KING, not solver)}
            bb.push(mv)
            if bb.is_check() and len(bb.checkers()) == 2:
                themes.add("doubleCheck")
            if moved:
                targets = [s for s in bb.attacks(mv.to_square) if (p := bb.piece_at(s)) and p.color != solver and (PIECE_VALUES[p.piece_type] > PIECE_VALUES[moved.piece_type] or p.piece_type == chess.KING or not bb.attackers(not solver, s))]
                if len(targets) >= 2:
                    themes.add("fork")
            for sq, old in before_attackers.items():
                if bb.piece_at(sq) and bb.piece_at(sq).color != solver:
                    new = set(bb.attackers(solver, sq)) - {mv.to_square}
                    if new - old:
                        themes.add("discoveredAttack")
            for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
                for sq in bb.pieces(pt, not solver):
                    if bb.is_pinned(not solver, sq) and bb.attackers(solver, sq):
                        themes.add("pin")
            if moved and moved.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN):
                for sq in bb.attacks(mv.to_square):
                    p = bb.piece_at(sq)
                    if p and p.color != solver and PIECE_VALUES[p.piece_type] >= 5:
                        df = (chess.square_file(sq) - chess.square_file(mv.to_square))
                        dr = (chess.square_rank(sq) - chess.square_rank(mv.to_square))
                        step_f = (df > 0) - (df < 0)
                        step_r = (dr > 0) - (dr < 0)
                        f, r = chess.square_file(sq) + step_f, chess.square_rank(sq) + step_r
                        while 0 <= f < 8 and 0 <= r < 8:
                            q = bb.piece_at(chess.square(f, r))
                            if q:
                                if q.color != solver and 0 < PIECE_VALUES[q.piece_type] < PIECE_VALUES[p.piece_type]:
                                    themes.add("skewer")
                                break
                            f += step_f
                            r += step_r
        else:
            bb.push(mv)
    ph = phase_of(board, board.ply())
    themes.add({OPENING: "opening", ENDGAME: "endgame"}.get(ph, "middlegame"))
    if ph == ENDGAME:
        kinds = {pt for c in (chess.WHITE, chess.BLACK) for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN) if board.pieces(pt, c)}
        if not kinds:
            themes.add("pawnEndgame")
        elif kinds == {chess.ROOK}:
            themes.add("rookEndgame")
        elif kinds == {chess.QUEEN}:
            themes.add("queenEndgame")
        elif kinds == {chess.BISHOP}:
            themes.add("bishopEndgame")
        elif kinds == {chess.KNIGHT}:
            themes.add("knightEndgame")
    themes.add("short" if n_solver <= 2 else "long")
    if "mate" not in themes:
        themes.add("crushing" if final_cp >= 500 else "advantage")
    return sorted(themes)


def rating_for(themes: list[str], moves: list[chess.Move], board: chess.Board) -> int:
    n_solver = (len(moves) + 1) // 2
    r = 900 + 180 * (n_solver - 1)
    if "mateIn1" in themes:
        r = 500 + (150 if "quietMove" in themes else 0)
    if "sacrifice" in themes:
        r += 250
    if "quietMove" in themes and "mateIn1" not in themes:
        r += 200
    if "hangingPiece" in themes:
        r -= 200
    if "discoveredAttack" in themes or "skewer" in themes:
        r += 100
    if "endgame" in themes:
        r += 100
    if board.is_capture(moves[0]) and "sacrifice" not in themes:
        r -= 80
    return max(400, min(2600, r))


async def scan_game(pool: EnginePool, game: chess.pgn.Game, source: dict, seen: set[str]) -> list[dict]:
    out = []
    board = game.board()
    prev_cp_white: int | None = None
    for mv in game.mainline_moves():
        board.push(mv)
        if board.ply() < 6 or board.is_game_over():
            continue
        lines = await _lines(pool, board, SCAN_DEPTH, 2)
        if len(lines) < 2:
            continue
        best_mv, best_cp, best_score, _ = lines[0]
        second_cp = lines[1][1]
        mate = _mate_distance(best_score, board.turn)
        if mate is None and (best_cp < MIN_RESULT_CP or best_cp - second_cp < MIN_GAP_CP):
            continue
        if mate is not None and lines[1][2].pov(board.turn).is_mate():
            continue  # two mating moves: not a puzzle
        # the puzzle starts before the opponent's last move
        pre = board.copy()
        pre.pop()
        key = pre.fen().split(" ")[0] + mv.uci()
        if key in seen:
            continue
        solution = await extend_solution(pool, board, best_mv)
        if not solution:
            continue
        end = board.copy()
        for s in solution:
            end.push(s)
        final_lines = [] if end.is_game_over() else await _lines(pool, end, 10, 1)
        final_cp = MATE_CP if end.is_checkmate() else (final_lines[0][1] if final_lines else 0)
        if not end.is_checkmate() and end.turn != board.turn:
            final_cp = -final_cp
        themes = themes_for(board, solution, final_cp)
        pid = "g" + hashlib.sha1(key.encode()).hexdigest()[:8]
        seen.add(key)
        out.append({
            "id": pid, "fen": pre.fen(), "moves": [mv.uci()] + [s.uci() for s in solution],
            "rating": rating_for(themes, solution, board), "rd": 90, "themes": themes,
            "source": {**source, "ply": board.ply()}, "popularity": 0,
        })
        _ = prev_cp_white
    return out


async def main(paths: list[str], out: Path, limit: int) -> None:
    pool = EnginePool()
    await pool.start()
    seen: set[str] = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                b = chess.Board(d["fen"])
                seen.add(b.fen().split(" ")[0] + d["moves"][0])
    total = 0
    try:
        with out.open("a", encoding="utf-8") as fh:
            for path in paths:
                with open(path, encoding="utf-8", errors="replace") as pg:
                    while True:
                        game = chess.pgn.read_game(pg)
                        if game is None:
                            break
                        source = {"white": game.headers.get("White", "?"), "black": game.headers.get("Black", "?"),
                                  "year": game.headers.get("Date", "????")[:4], "event": game.headers.get("Event", ""), "file": Path(path).name}
                        found = await scan_game(pool, game, source, seen)
                        for p in found:
                            fh.write(json.dumps(p) + "\n")
                        fh.flush()
                        total += len(found)
                        print(f"{Path(path).name}: {source['white']} vs {source['black']} -> {len(found)} puzzles (total {total})")
                        if total >= limit:
                            return
    finally:
        await pool.stop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pgns", nargs="+")
    ap.add_argument("--out", default="data/puzzles/generated.jsonl")
    ap.add_argument("--limit", type=int, default=100000)
    a = ap.parse_args()
    asyncio.run(main(a.pgns, Path(a.out), a.limit))
