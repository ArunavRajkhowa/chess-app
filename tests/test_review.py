"""Game Review: classification rules, accuracy maths, and the full pipeline on a short game."""
from __future__ import annotations

import time

import chess
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.review import classify as C
from backend.review.phases import ENDGAME, OPENING, phase_of


def judge(**kw):
    base = dict(win_before=60.0, win_after=60.0, second_best_win=55.0, is_best=False, is_book=False, is_forced=False,
                cp_loss=0, sacrificed_pawns=0, opponent_prev_class=None, best_win_was_available=60.0)
    base.update(kw)
    return C.classify_move(**base)


@pytest.mark.parametrize("drop,expected", [(0.5, C.EXCELLENT), (3, C.GOOD), (7, C.INACCURACY), (15, C.MISTAKE), (30, C.BLUNDER)])
def test_drop_ladder(drop, expected):
    assert judge(win_after=60.0 - drop, cp_loss=int(drop * 10)) == expected


def test_special_labels():
    assert judge(is_forced=True) == C.FORCED
    assert judge(is_book=True) == C.BOOK
    assert judge(is_best=True) == C.BEST
    assert judge(is_best=True, second_best_win=40.0) == C.GREAT
    assert judge(is_best=True, opponent_prev_class=C.BLUNDER) == C.GREAT
    assert judge(is_best=True, sacrificed_pawns=3, win_before=70.0, win_after=70.0) == C.BRILLIANT
    assert judge(is_best=True, sacrificed_pawns=3, win_before=99.0, win_after=99.0, second_best_win=98.0) == C.BEST
    assert judge(win_before=95.0, win_after=60.0, best_win_was_available=95.0, cp_loss=400) == C.MISS


def test_game_accuracy_rewards_consistency():
    flat = C.game_accuracy([50] * 21, [95] * 20)
    spiky = C.game_accuracy([50, 90, 10] * 7, [95] * 20)
    assert 90 < flat <= 100
    assert abs(flat - spiky) < 6
    assert C.estimate_rating(10) > C.estimate_rating(50) > C.estimate_rating(150)


def test_phase_detection():
    assert phase_of(chess.Board(), 0) == OPENING
    assert phase_of(chess.Board("8/8/4k3/8/8/4K3/4P3/8 w - - 0 1"), 60) == ENDGAME


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    with TestClient(create_app()) as c:
        yield c


def _wait(client, job_id, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/review/jobs/{job_id}").json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.3)
    raise AssertionError("review did not finish")


def test_review_scholars_mate_import(client):
    pgn = '[White "A"]\n[Black "B"]\n[Result "1-0"]\n\n1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0'
    r = client.post("/api/review/import", json={"pgn": pgn, "mode": "quick"})
    assert r.status_code == 200, r.text
    body = r.json()
    job = _wait(client, body["job"]["id"])
    assert job["status"] == "done", job
    rep = job["report"]
    assert len(rep["moves"]) == 7
    assert rep["moves"][5]["classification"] == C.BLUNDER  # 3...Nf6?? allows mate
    assert rep["moves"][6]["classification"] in (C.BEST, C.GREAT)
    assert rep["moves"][6]["eval_after_text"] == "#"
    assert rep["white"]["accuracy"] > rep["black"]["accuracy"]
    assert rep["opening"] is not None
    assert 6 in rep["key_moments"]
    stored = client.get(f"/api/review/games/{body['game_id']}").json()
    assert stored["report"]["white"]["accuracy"] == rep["white"]["accuracy"]
    assert client.get("/api/play/games").json()["games"][0]["source"] == "import"


def test_bad_pgn_rejected(client):
    assert client.post("/api/review/import", json={"pgn": "1. e4 e4 2. Nf3", "mode": "quick"}).status_code == 400
    assert client.post("/api/review/import", json={"pgn": "[Event \"x\"]\n\n*", "mode": "quick"}).status_code == 400


def test_insights_from_a_reviewed_bot_game(client):
    assert client.get("/api/insights/me").json()["games"] == 0
    game = client.post("/api/play/games", json={"bot_id": "pip", "player_color": "white"}).json()
    for mv in ["e2e4", "d1h5", "f1c4", "h5f7"]:
        r = client.post(f"/api/play/games/{game['id']}/move", json={"move": mv})
        if r.status_code != 200:
            break
        game = r.json()["game"]
        if game["status"] == "finished":
            break
    if game["status"] == "active":
        game = client.post(f"/api/play/games/{game['id']}/resign").json()
    job = client.post(f"/api/review/games/{game['id']}", json={"mode": "quick"}).json()
    _wait(client, job["id"])
    ins = client.get("/api/insights/me").json()
    assert ins["games"] == 1
    assert 0 <= ins["accuracy"]["mean"] <= 100
    assert sum(ins["results"].values()) == 1
    assert "move_quality" in ins and "shapes" in ins
