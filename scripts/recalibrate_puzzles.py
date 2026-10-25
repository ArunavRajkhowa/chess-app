"""Rewrites every puzzle's rating (backend/puzzles/difficulty.py: the measured rating when it has one, else
its shape) and resets its rating deviation, keeping everything else. Usage: python -m scripts.recalibrate_puzzles [--dry]"""
from __future__ import annotations

import collections
import json
import sys

from backend.puzzles.difficulty import difficulty
from backend.settings import REPO_ROOT

RD = 100


def main(dry: bool) -> None:
    before: collections.Counter = collections.Counter()
    after: collections.Counter = collections.Counter()
    for path in sorted((REPO_ROOT / "data" / "puzzles").glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for r in rows:
            before[r["rating"] // 200 * 200] += 1
            r["rating"] = difficulty(r["fen"], r["moves"], r["themes"], measured=r.get("rating_measured"))
            r["rd"] = RD
            after[r["rating"] // 200 * 200] += 1
        if not dry:
            path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print("before:", sorted(before.items()))
    print("after: ", sorted(after.items()))


if __name__ == "__main__":
    main("--dry" in sys.argv)
    sys.exit(0)
