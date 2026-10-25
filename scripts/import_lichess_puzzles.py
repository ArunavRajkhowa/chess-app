"""Samples a balanced puzzle set from the lichess puzzle database (CC0) into data/puzzles/lichess.jsonl.
The CSV downloads into --dir, a directory of its own, because the file is untrusted data.
Usage: python -m scripts.import_lichess_puzzles --dir <download dir> [--per-cell 10]"""
from __future__ import annotations

import argparse
import collections
import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

import zstandard

from backend.puzzles.difficulty import difficulty
from backend.settings import REPO_ROOT

URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
OUT = REPO_ROOT / "data" / "puzzles" / "lichess.jsonl"
MIN_POPULARITY, MIN_PLAYS, MAX_RD = 80, 500, 100
MIN_RATING, MAX_RATING, BAND = 400, 2600, 200  # bands [400,600) ... [2400,2600)
SOURCE_TAGS = {"master", "masterVsMaster", "superGM"}  # who played the game, not what the puzzle trains


def download(path: Path) -> None:
    print(f"downloading {URL} -> {path}", flush=True)
    with urllib.request.urlopen(URL) as resp, path.open("wb") as out:  # noqa: S310 (fixed https URL)
        while chunk := resp.read(1 << 20):
            out.write(chunk)


def rows(path: Path):
    with path.open("rb") as fh:
        reader = csv.DictReader(io.TextIOWrapper(zstandard.ZstdDecompressor().stream_reader(fh), encoding="utf-8", newline=""))
        yield from reader


def convert(row: dict) -> dict:
    themes = [t for t in row["Themes"].split() if t not in SOURCE_TAGS]
    measured = int(row["Rating"])
    moves = row["Moves"].split()
    return {
        "id": f"lichess:{row['PuzzleId']}", "fen": row["FEN"], "moves": moves,
        "rating": difficulty(row["FEN"], moves, themes, measured=measured), "rating_measured": measured,
        "rd": int(row["RatingDeviation"]), "themes": themes,
        "source": {"url": row["GameUrl"], "event": "lichess"},
        "opening_tags": row["OpeningTags"].split(), "popularity": int(row["Popularity"]),
    }


def sample(path: Path, per_cell: int) -> list[dict]:
    """One pass: a puzzle is kept when it fills at least one (theme, band) cell still under quota.
    Rows arrive in id order, which says nothing about rating or theme, so the pass is a fair draw."""
    cells: collections.Counter = collections.Counter()
    kept: list[dict] = []
    scanned = qualifying = 0
    for row in rows(path):
        scanned += 1
        rating = int(row["Rating"])
        if not (MIN_RATING <= rating < MAX_RATING) or int(row["Popularity"]) < MIN_POPULARITY \
                or int(row["NbPlays"]) < MIN_PLAYS or int(row["RatingDeviation"]) > MAX_RD:
            continue
        qualifying += 1
        # One cell per (theme, 200-point rating band), so every theme gets puzzles at every level.
        band = rating // BAND * BAND
        keys = [(t, band) for t in row["Themes"].split() if t not in SOURCE_TAGS]
        if not any(cells[k] < per_cell for k in keys):
            continue
        for k in keys:
            cells[k] += 1
        kept.append(convert(row))
    print(f"scanned {scanned} rows, {qualifying} qualifying, kept {len(kept)}", flush=True)
    return kept


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="download directory for the CSV (untrusted data; nothing else in it)")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--per-cell", type=int, default=10, help="puzzles per (theme, 200-point band) cell")
    a = ap.parse_args()
    src = Path(a.dir) / URL.rsplit("/", 1)[1]
    if not src.exists():
        src.parent.mkdir(parents=True, exist_ok=True)
        download(src)
    kept = sample(src, a.per_cell)
    out = Path(a.out)
    with out.open("w", encoding="utf-8") as fh:
        for p in kept:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    bands = collections.Counter(p["rating"] // BAND * BAND for p in kept)
    themes = collections.Counter(t for p in kept for t in p["themes"])
    print(f"wrote {len(kept)} puzzles to {out}")
    print("by band:", sorted(bands.items()))
    print("by theme:", themes.most_common())
    return 0


if __name__ == "__main__":
    sys.exit(main())
