"""Maia-3 5M (CSSLab, AGPL-3.0): predicts the move a human of a given rating plays, on the CPU.
The network is data/maia/maia3-5m.onnx (made by scripts/export_maia3.py); data/maia/NOTICE names
its source. The input encoding is a numpy port of maia3/dataset.py at the pinned upstream commit."""
from __future__ import annotations

import threading
from pathlib import Path

import chess
import numpy as np

MODEL_PATH = Path(__file__).resolve().parents[2] / "data" / "maia" / "maia3-5m.onnx"
HISTORY = 8  # positions the model reads: the current one and up to seven before it (upstream "history")
PROMOTIONS = "qrbn"  # upstream vocabulary order of the promotion piece

_lock = threading.Lock()
_session = None  # onnxruntime.InferenceSession, made on the first call


def _planes(board: chess.Board) -> np.ndarray:
    """Return the (64, 12) one-hot piece planes, seen from the side to move."""
    if board.turn == chess.BLACK:
        board = board.mirror()
    planes = np.zeros((64, 12), dtype=np.float32)
    for square, piece in board.piece_map().items():
        planes[square, piece.piece_type - 1 + (6 if piece.color == chess.BLACK else 0)] = 1.0
    return planes


def encode(board: chess.Board) -> np.ndarray:
    """Return the (64, 97) model input: 8 positions from board.move_stack, oldest first.
    A short history repeats its earliest position; the last column (clock) is zero."""
    past = board.copy()
    planes = [_planes(past)]
    while len(planes) < HISTORY and past.move_stack:
        past.pop()
        planes.append(_planes(past))
    planes += [planes[-1]] * (HISTORY - len(planes))
    planes.reverse()
    planes.append(np.zeros((64, 1), dtype=np.float32))
    return np.concatenate(planes, axis=1)


def move_index(move: chess.Move, turn: chess.Color) -> int:
    """Return the move's index in the upstream 4352-move vocabulary (board mirrored for Black)."""
    src, dst = move.from_square, move.to_square
    if turn == chess.BLACK:
        src, dst = chess.square_mirror(src), chess.square_mirror(dst)
    if move.promotion:
        promo = PROMOTIONS.index(chess.piece_symbol(move.promotion))
        return 4096 + chess.square_file(src) * 32 + chess.square_file(dst) * 4 + promo
    return src * 64 + dst


def _get_session():
    global _session
    with _lock:
        if _session is None:
            import onnxruntime as ort

            options = ort.SessionOptions()
            options.intra_op_num_threads = 1
            options.inter_op_num_threads = 1
            _session = ort.InferenceSession(str(MODEL_PATH), options, providers=["CPUExecutionProvider"])
    return _session


def predict(board: chess.Board, elo_self: int, elo_oppo: int) -> tuple[dict[chess.Move, float], tuple[float, float, float]]:
    """Return (legal move -> probability, (win, draw, loss) for the side to move).
    Raises ValueError when the position has no legal move."""
    legal = list(board.legal_moves)
    if not legal:
        raise ValueError(f"board has no legal move: fen {board.fen()!r}, expected a position with a move to play")
    logits, value = _get_session().run(None, {
        "tokens": encode(board)[None],
        "elo_self": np.array([elo_self], dtype=np.int64),
        "elo_oppo": np.array([elo_oppo], dtype=np.int64),
    })
    chosen = logits[0, [move_index(m, board.turn) for m in legal]].astype(np.float64)
    probs = np.exp(chosen - chosen.max())
    probs /= probs.sum()
    wdl = np.exp(value[0].astype(np.float64) - value[0].max())
    loss, draw, win = wdl / wdl.sum()  # upstream value order: loss, draw, win
    return dict(zip(legal, probs.tolist(), strict=True)), (float(win), float(draw), float(loss))


def policy(board: chess.Board, elo_self: int, elo_oppo: int) -> dict[chess.Move, float]:
    """Return legal move -> probability that a player rated elo_self (facing elo_oppo) plays it."""
    return predict(board, elo_self, elo_oppo)[0]
