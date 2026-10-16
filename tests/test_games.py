from __future__ import annotations

import re

import chess

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.content.games import load_games


def test_seed_games_load_with_comments():
    games = load_games()
    g = next(x for x in games if x.white == "Paul Morphy")
    assert g.result == "1-0" and g.plies[-1]["san"] == "Rd8#"
    assert len(g.key_moments) >= 4 and "development" in g.themes


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    with TestClient(create_app()) as c:
        yield c


def test_games_api_and_guess(client):
    idx = client.get("/api/games").json()
    assert idx["total"] >= 1 and any(t["key"] == "attack" for t in idx["themes"])
    gid = idx["games"][0]["id"]
    d = client.get(f"/api/games/{gid}").json()
    assert d["moves"][0]["san"] == "e4" and d["pgn"].startswith("[Event")
    r = client.post("/api/games/guess", json={"game_id": gid, "ply": 1, "move": "e2e4"}).json()
    assert r["verdict"] == "master" and r["points"] == 3
    r = client.post("/api/games/guess", json={"game_id": gid, "ply": 1, "move": "d2d4"}).json()
    assert r["verdict"] in ("excellent", "good") and r["master_san"] == "e4"
    r = client.post("/api/games/guess", json={"game_id": gid, "ply": 31, "move": "b3b8"}).json()
    assert r["verdict"] == "master"
    assert client.post("/api/games/guess", json={"game_id": gid, "ply": 1, "move": "e2e5"}).status_code == 400
    assert client.get("/api/games?theme=attack").json()["games"]


_SAN = r"(?:O-O-O|O-O|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?)[+#]?[!?]*"
_TOKEN = re.compile(r"(\d{1,3})\.(\.\.\.|\.\.|…)?\s?(" + _SAN + r")|(" + _SAN + r")")


def _numbered_lines(comment: str) -> list[tuple[int, list[str]]]:
    """Move sequences a note names: each starts at a numbered move ("12.Nxa4", "22...Rg2") and
    continues through the SAN tokens that follow it with only spaces between."""
    lines: list[tuple[int, list[str]]] = []
    current: list[str] | None = None
    last_end = None
    for m in _TOKEN.finditer(comment):
        joined = last_end is not None and comment[last_end:m.start()].strip() == ""
        if m.group(1):
            ply = 2 * int(m.group(1)) - (0 if m.group(2) else 1)
            if current is not None and joined and ply == lines[-1][0] + len(current):
                current.append(m.group(3))
            else:
                current = [m.group(3)]
                lines.append((ply, current))
        elif current is not None and joined:
            current.append(m.group(4))
        else:
            current = None
        last_end = m.end()
    return lines


def test_every_line_in_a_master_game_note_is_legal():
    """A note's line must replay from the game position at its first move, or continue the line
    before it in the same note (a variation)."""
    bad = []
    for g in load_games():
        fens = [chess.STARTING_FEN] + [p["fen"] for p in g.plies]
        for p in g.plies:
            prev_end: tuple[int, chess.Board] | None = None
            for ply, sans in _numbered_lines(p["comment"] or ""):
                starts = [chess.Board(fens[ply - 1])] if 1 <= ply <= len(fens) else []
                if prev_end and prev_end[0] == ply:
                    starts.append(prev_end[1])
                end = None
                for b in starts:
                    try:
                        for san in sans:
                            b.push_san(san.rstrip("!?"))
                        end = b
                        break
                    except ValueError:
                        continue
                if end is None:
                    bad.append(f"{g.id} ply {p['ply']}: {' '.join(sans)} from move {(ply + 1) // 2}")
                    prev_end = None
                else:
                    prev_end = (ply + len(sans), end)
    assert not bad, "\n".join(bad)
