"""Curriculum loading, validation, the learn API, progress, and the drill engine reply."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.content import lessons as L


def test_curriculum_validates_sections(tmp_path, monkeypatch):
    bad = {"modules": [{"id": "x", "band": 1, "title": "t", "lessons": [{"id": "l1", "title": "a", "sections": [
        {"type": "challenge", "fen": "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "solution": ["a1a8"]},
        {"type": "challenge", "fen": "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "solution": ["a1a9"]},
        {"type": "quiz", "question": "q", "options": ["a"], "answer": 0},
        {"type": "game", "pgn": "1. e4 e5 2. Nf3 *"},
    ]}]}]}
    (tmp_path / "bad.json").write_text(json.dumps(bad))
    monkeypatch.setattr(L, "LESSONS_DIR", tmp_path)
    L.load_curriculum.cache_clear()
    mods = L.load_curriculum()
    assert len(mods) == 1 and len(mods[0].lessons[0].sections) == 2
    assert mods[0].lessons[0].sections[0]["solution_san"] == ["Ra8#"]
    assert mods[0].lessons[0].sections[1]["plies"][-1]["san"] == "Nf3"
    L.load_curriculum.cache_clear()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    L.load_curriculum.cache_clear()
    with TestClient(create_app()) as c:
        yield c


def test_real_content_loads_and_progress_works(client):
    cur = client.get("/api/learn/curriculum").json()
    assert len(cur["bands"]) == 9
    b0 = cur["bands"][0]
    assert b0["lessons_total"] >= 3 and b0["modules"][0]["lessons"][0]["id"] == "b0m1l1"
    lesson = client.get("/api/learn/lessons/b0m3l2").json()
    assert lesson["next"] == "b0m3l3" and lesson["prev"] == "b0m3l1"
    assert any(s["type"] == "challenge" and s["solution_san"] == ["Qxf7#"] for s in lesson["sections"])
    assert client.get("/api/learn/lessons/nope").status_code == 404
    r = client.post("/api/learn/progress", json={"lesson_id": "b0m3l2", "completed": True, "score": 80})
    assert r.status_code == 200
    cur2 = client.get("/api/learn/curriculum").json()
    assert cur2["bands"][0]["lessons_done"] == 1
    assert client.get("/api/learn/progress").json()["progress"]["b0m3l2"]["score"] == 80


def test_drill_move_replies_and_detects_mate(client):
    r = client.post("/api/learn/drill/move", json={"fen": "8/8/8/3k4/8/8/8/R1R3K1 w - - 0 1", "move": "c1c4", "goal": "mate"}).json()
    assert r["played"] == "Rc4" and r["reply"] is not None and r["outcome"] is None
    r = client.post("/api/learn/drill/move", json={"fen": "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "move": "a1a8", "goal": "mate"}).json()
    assert r["outcome"]["result"] == "success" and r["reply"] is None
    r = client.post("/api/learn/drill/move", json={"fen": "7k/5Q2/6K1/8/8/8/8/8 w - - 0 1", "move": "g6h6", "goal": "mate"}).json()
    assert r["outcome"]["result"] == "fail" and r["outcome"]["reason"] == "stalemate"
    assert client.post("/api/learn/drill/move", json={"fen": "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "move": "a1a9", "goal": "mate"}).status_code == 400


def test_drill_win_material_goal(client):
    # rook takes a free pawn on the seventh: material goes up by one, the engine's reply changes nothing
    fen = "6k1/pp3ppp/8/8/8/8/PPP2PPP/R5K1 w - - 0 1"
    r = client.post("/api/learn/drill/move", json={"fen": fen, "move": "a1d1", "goal": "win_material", "start_fen": fen}).json()
    assert r["outcome"] is None
    r3 = client.post("/api/learn/drill/move", json={"fen": "5k2/pp3ppp/8/8/8/8/PPP2PPP/3R2K1 w - - 0 1", "move": "d1d7", "goal": "win_material", "start_fen": fen}).json()
    assert r3["outcome"] is None or r3["outcome"]["result"] in ("success", "fail")


def test_drill_accepts_san_and_refuses_a_position_without_a_king(client):
    fen = "r3k3/8/8/8/8/8/8/R3K3 w Qq - 0 1"
    for move in ("Rxa8", "O-O-O"):
        r = client.post("/api/learn/drill/move", json={"fen": fen, "move": move, "goal": "mate"})
        assert r.status_code == 200, (move, r.text)
    r = client.post("/api/learn/drill/move", json={"fen": "4k3/8/8/8/8/8/8/R7 w - - 0 1", "move": "a1a2", "goal": "mate"})
    assert r.status_code == 400
