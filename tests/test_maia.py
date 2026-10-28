"""Maia-3 runtime against fixtures made once from the upstream torch code (maia3 commit 1e13597):
the numpy encoder equals maia3's tokens, and the ONNX model picks torch's top move."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import chess
import numpy as np
import pytest

from backend.bots import maia

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = json.loads((FIXTURES / "maia3_golden.json").read_text(encoding="utf-8"))
TOKENS = np.load(FIXTURES / "maia3_tokens.npz")


def _board(fen: str, moves: list[str]) -> chess.Board:
    board = chess.Board(fen)
    for move in moves:
        board.push_uci(move)
    return board


def test_import_does_not_load_the_model():
    code = "import sys; import backend.bots.maia as m; print(m._session is None, 'onnxruntime' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                         cwd=Path(__file__).parent.parent).stdout.split()
    assert out == ["True", "False"]


@pytest.mark.parametrize("index", range(len(GOLDEN["tokens"])), ids=[c["name"] for c in GOLDEN["tokens"]])
def test_encoder_matches_reference(index):
    case = GOLDEN["tokens"][index]
    got = maia.encode(_board(case["fen"], case["moves"]))
    assert got.shape == (64, 97) and got.dtype == np.float32
    assert np.array_equal(got, TOKENS[f"case{index}"].astype(np.float32))


def test_policy_is_legal_and_sums_to_one():
    for case in GOLDEN["top1"][:10] + [{"moves": [], "elo_self": 1500, "elo_oppo": 1500}]:
        board = _board(chess.STARTING_FEN, case["moves"])
        probs = maia.policy(board, case["elo_self"], case["elo_oppo"])
        assert set(probs) == set(board.legal_moves)
        assert sum(probs.values()) == pytest.approx(1.0, abs=1e-9)
        assert all(p >= 0 for p in probs.values())


def test_top1_matches_torch():
    misses = []
    for case in GOLDEN["top1"]:
        probs = maia.policy(_board(chess.STARTING_FEN, case["moves"]), case["elo_self"], case["elo_oppo"])
        best = max(probs, key=probs.get).uci()
        if best != case["top1"]:
            misses.append((len(case["moves"]), case["elo_self"], best, case["top1"]))
    assert not misses, misses
    assert len(GOLDEN["top1"]) == 50


def test_value_is_a_distribution():
    _probs, wdl = maia.predict(chess.Board(), 1500, 1500)
    assert sum(wdl) == pytest.approx(1.0) and all(0 <= p <= 1 for p in wdl)


def test_no_legal_move_raises():
    mate = _board(chess.STARTING_FEN, ["f2f3", "e7e5", "g2g4", "d8h4"])
    with pytest.raises(ValueError, match="no legal move"):
        maia.policy(mate, 1500, 1500)
