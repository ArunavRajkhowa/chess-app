"""Engine locator, pool and score math. Starts a real engine process once per session."""
from __future__ import annotations

import asyncio

import chess
import chess.engine
import pytest

from backend.engine import score as sc
from backend.engine.locator import find_engine_command
from backend.engine.pool import EnginePool


def test_locator_finds_some_engine():
    cmd = find_engine_command()
    assert cmd and cmd[0]


@pytest.mark.parametrize(
    "cp,expected",
    [(0, 50.0), (100, 59.1), (-100, 40.9), (1000, 97.5), (sc.MATE_CP, 100.0), (-sc.MATE_CP, 0.0)],
)
def test_win_percent_curve(cp, expected):
    assert abs(sc.win_percent_from_cp(cp) - expected) < 0.15


def test_mate_scores_order_faster_mate_higher():
    m1 = chess.engine.PovScore(chess.engine.Mate(1), chess.WHITE)
    m5 = chess.engine.PovScore(chess.engine.Mate(5), chess.WHITE)
    assert sc.cp_from_score(m1) > sc.cp_from_score(m5) > 0
    assert sc.describe_score(m1) == "M1"
    assert sc.describe_score(chess.engine.PovScore(chess.engine.Mate(-2), chess.WHITE)) == "-M2"
    assert sc.describe_score(chess.engine.PovScore(chess.engine.Cp(35), chess.WHITE)) == "+0.35"


def test_move_accuracy_bounds():
    assert sc.move_accuracy(50, 50) >= 99.99
    assert sc.move_accuracy(50, 70) >= 99.99
    assert 0 <= sc.move_accuracy(80, 20) < 20


def test_pool_analyse_and_play(event_loop):
    async def run():
        pool = EnginePool()
        await pool.start()
        try:
            board = chess.Board()
            infos = await pool.analyse(board, depth=8, multipv=3)
            assert 1 <= len(infos) <= 3
            assert infos[0]["pv"][0] in board.legal_moves
            weak = await pool.play_move(
                board, options={"UCI_LimitStrength": True, "UCI_Elo": 1320, "Skill Level": 0},
                depth=6, multipv=2,
            )
            assert weak[0]["pv"][0] in board.legal_moves
        finally:
            await pool.stop()

    event_loop.run_until_complete(run())
