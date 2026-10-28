"""Exports Maia-3 5M (CSSLab, AGPL-3.0) to data/maia/maia3-5m.onnx and checks the export against torch.
Downloads the pinned checkpoint and refuses it when its sha256 differs. Usage: python -m scripts.export_maia3"""
# The app needs only onnxruntime and numpy. This script also needs the export toolchain, pinned to the
# versions the committed file was made with (python 3.12, linux amd64):
#   pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
#   pip install onnx==1.19.1 onnxscript==0.7.2 onnxruntime==1.23.2 chess==1.11.2 \
#       https://github.com/CSSLab/maia3/archive/1e13597c42d4858b7cfd7cfdae01e297263364b2.tar.gz
from __future__ import annotations

import argparse
import hashlib
import random
import tempfile
import urllib.request
from collections import deque
from pathlib import Path

import chess
import numpy as np

REPO = "UofTCSSLab/Maia3-5M"
REVISION = "b6559de2398d7140b985f28fd2c19fb5e47ddabe"
CHECKPOINT = "maia3-5m.pt"
CHECKPOINT_SHA256 = "ba14208b2992d85502f5fb501934abf6aaaeb355e9f3fdf90e326911f562524f"
OUT = Path(__file__).resolve().parent.parent / "data" / "maia" / "maia3-5m.onnx"
CHECK_POSITIONS = 300
MIN_TOP1_AGREEMENT = 0.99


def download(folder: Path) -> Path:
    """Download the pinned checkpoint into folder; raise when its sha256 is not the pinned one."""
    path = folder / CHECKPOINT
    url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{CHECKPOINT}"
    urllib.request.urlretrieve(url, path)  # noqa: S310 - a fixed https URL
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != CHECKPOINT_SHA256:
        raise ValueError(f"{url}: sha256 {digest}, expected {CHECKPOINT_SHA256}")
    return path


def main() -> None:
    import torch
    from maia3 import uci
    from maia3.dataset import get_historical_tokens, get_legal_moves_mask, tokenize_board
    from torch.onnx import symbolic_helper

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        cfg = uci.parse_args(["--model", "maia3-5m", "--checkpoint-path", str(download(Path(tmp))),
                              "--device", "cpu", "--no-use-amp"])
        model = uci.load_model(cfg)

    class PolicyValue(torch.nn.Module):
        def __init__(self, inner):
            super().__init__()
            self.inner = inner

        def forward(self, tokens, elo_self, elo_oppo):
            logits_move, logits_value, _ponder = self.inner(tokens, elo_self, elo_oppo)
            return logits_move, logits_value

    def rms_norm(g, x, shape, weight, eps):
        # The legacy exporter has no aten::rms_norm. torch's default eps is the dtype's epsilon.
        value = symbolic_helper._maybe_get_const(eps, "f")
        value = float(torch.finfo(torch.float32).eps) if not isinstance(value, float) else value
        mean_square = g.op("ReduceMean", g.op("Mul", x, x), axes_i=[-1], keepdims_i=1)
        y = g.op("Div", x, g.op("Sqrt", g.op("Add", mean_square, g.op("Constant", value_t=torch.tensor(value)))))
        return y if symbolic_helper._is_none(weight) else g.op("Mul", y, weight)

    torch.onnx.register_custom_op_symbolic("aten::rms_norm", rms_norm, 17)
    wrapped = PolicyValue(model).eval()

    def tokens_of(moves: list[chess.Move]) -> tuple[torch.Tensor, chess.Board]:
        board = chess.Board()
        history = deque([tokenize_board(board)], maxlen=cfg.history)
        for move in moves:
            board.push(move)
            history.append(tokenize_board(board))
        return get_historical_tokens(history, cfg, 0.0, 0.0, 0.0, 0.0).unsqueeze(0), board

    sample, _ = tokens_of([])
    elo = torch.tensor([1500])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(wrapped, (sample, elo, elo), str(args.out), input_names=["tokens", "elo_self", "elo_oppo"],
                      output_names=["policy", "value"], opset_version=17, dynamo=False)

    # Check: positions from seeded random games, torch and onnxruntime fed the same reference tokens.
    import onnxruntime as ort

    session = ort.InferenceSession(str(args.out), providers=["CPUExecutionProvider"])
    all_moves = uci.Maia3UCIEngine(cfg).all_moves_dict
    rng = random.Random(0)
    agree = checked = 0
    worst = 0.0
    for _ in range(CHECK_POSITIONS):
        board, moves = chess.Board(), []
        for _ply in range(rng.randrange(0, 80)):
            legal = list(board.legal_moves)
            if not legal:
                break
            moves.append(rng.choice(legal))
            board.push(moves[-1])
        tokens, board = tokens_of(moves)
        if board.is_game_over():
            continue
        e_self, e_oppo = torch.tensor([rng.randrange(600, 2600)]), torch.tensor([rng.randrange(600, 2600)])
        with torch.no_grad():
            want = wrapped(tokens, e_self, e_oppo)[0][0].numpy()
        got = session.run(None, {"tokens": tokens.numpy(), "elo_self": e_self.numpy(), "elo_oppo": e_oppo.numpy()})[0][0]
        mask = get_legal_moves_mask(board, all_moves).numpy()
        checked += 1
        agree += int(np.where(mask, want, -np.inf).argmax() == np.where(mask, got, -np.inf).argmax())
        worst = max(worst, float(np.abs(want - got).max()))
    digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
    print(f"{args.out}: {args.out.stat().st_size} bytes, sha256 {digest}")
    print(f"top-1 agreement with torch {agree}/{checked}, max abs logit difference {worst:.2e}")
    if agree < MIN_TOP1_AGREEMENT * checked:
        raise SystemExit(f"top-1 agreement {agree}/{checked} is below {MIN_TOP1_AGREEMENT:.0%}")


if __name__ == "__main__":
    main()
