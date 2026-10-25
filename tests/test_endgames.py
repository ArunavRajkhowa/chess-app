"""Endgame trainer: every position is legal and its goal agrees with the engine's verdict."""
from __future__ import annotations

import chess
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.bots.guide import DRAW_CP, WIN_CP
from backend.content.endgames import load_endgames
from backend.engine.pool import EnginePool
from backend.engine.score import cp_from_score
from backend.routers.endgames import judge_line


def test_goals_agree_with_the_engine(event_loop):
    async def run():
        pool = EnginePool()
        await pool.start()
        bad = []
        try:
            for p in load_endgames()["positions"]:
                board = chess.Board(p["fen"])
                infos = await pool.analyse(board, depth=18)
                cp = cp_from_score(infos[0]["score"], board.turn)
                if p["goal"] in ("mate", "promote", "win_material") and cp < WIN_CP:
                    bad.append((p["key"], cp))
                if p["goal"] in ("draw", "survive") and cp < -DRAW_CP:
                    bad.append((p["key"], cp))
        finally:
            await pool.stop()
        assert not bad, bad

    event_loop.run_until_complete(run())


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    with TestClient(create_app()) as c:
        yield c


def test_endgame_api(client):
    idx = client.get("/api/endgames").json()
    assert len(idx["themes"]) == 5 and len(idx["positions"]) >= 20
    assert all(p["best"] is None for p in idx["positions"])
    ch = client.get("/api/endgames/challenge", params={"theme": "rook"}).json()
    assert 1 <= len(ch["positions"]) <= 5 and all(p["theme"] == "rook" for p in ch["positions"])
    assert client.get("/api/endgames/challenge", params={"theme": "nope"}).status_code == 404
    r = client.post("/api/endgames/attempt", json={"key": "mate-two-rooks", "line": [], "seconds": 1}).json()
    assert r["success"] is False and r["stats"]["solved"] == 0 and r["stats"]["tried"] == 1  # a claim with no moves wins nothing
    ladder = ["a1a5", "d5d6", "c1c2", "d6d7", "a5a6", "d7e7", "c2c1", "e7d7", "c1c6", "d7e8", "a6a7", "e8d8", "a7b7", "d8e8", "c6c8"]
    r = client.post("/api/endgames/attempt", json={"key": "mate-two-rooks", "line": ladder, "seconds": 40.2}).json()
    assert r["success"] is True and r["stats"]["solved"] == 1 and r["stats"]["best_moves"] == 8
    assert client.post("/api/endgames/attempt", json={"key": "mate-two-rooks", "line": ["a1a9"], "seconds": 1}).status_code == 400
    assert client.post("/api/endgames/attempt", json={"key": "mate-two-rooks", "line": [], "seconds": -5}).status_code == 422
    assert client.post("/api/endgames/attempt", json={"key": "nope", "line": [], "seconds": 1}).status_code == 404


def test_letting_the_pawn_promote_and_taking_the_new_queen_still_wins():
    p = next(p for p in load_endgames()["positions"] if p["key"] == "queen-vs-knight-pawn")
    line = ["g1f2", "a2b3", "f2f5", "b2b1q", "f5b1", "b3c4", "b1b6", "c4d5", "h8g7", "d5e5", "g7g6", "e5f4", "g6f6", "f4e4",
            "b6b5", "e4e3", "f6f5", "e3d2", "f5e4", "d2c3", "e4e3", "c3c2", "b5b4", "c2c1", "e3d3", "c1d1", "b4b1"]  # ends in mate
    assert judge_line(p, line) == (True, 14)
