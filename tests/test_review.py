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


def test_book_line_blunder_and_losing_miss_are_blunders():
    assert judge(is_book=True, win_before=50.0, win_after=41.0, cp_loss=90) == C.BOOK  # dubious theory stays book
    assert judge(is_book=True, win_before=43.5, win_after=0.0, cp_loss=10000) == C.BLUNDER  # 2.g4?? in the Fool's mate line
    assert judge(win_before=100.0, win_after=20.0, best_win_was_available=100.0, cp_loss=1000) == C.BLUNDER  # missed mate and lost
    assert judge(win_before=100.0, win_after=99.9, best_win_was_available=100.0, cp_loss=9000, mate_missed=True) == C.MISS  # Qa3 for Rd8#


def test_game_accuracy_weights_each_move_by_its_own_ply():
    # 5 positions -> window 2; white moves are plies 1 and 3, whose windows are (50,50) and (50,90).
    weights = C.volatility_weights([50, 50, 50, 90, 10])
    assert weights == [0.5, 0.5, 12.0, 12.0]
    assert C.game_accuracy([100.0, 50.0], weights[0::2]) == 59.3  # (52.0 weighted + 66.7 harmonic) / 2


def test_game_accuracy_rewards_consistency():
    flat = C.game_accuracy([95] * 20, C.volatility_weights([50] * 21)[0::2])
    spiky = C.game_accuracy([95] * 20, C.volatility_weights([50, 90, 10] * 7)[0::2])
    assert 90 < flat <= 100
    assert abs(flat - spiky) < 6
    assert C.estimate_rating(10) > C.estimate_rating(50) > C.estimate_rating(150)


def test_a_sacrifice_can_leave_another_piece_hanging():
    from backend.review.report import _sacrificed_pawns
    board = chess.Board()
    for san in "Nf3 Nf6 c4 g6 Nc3 Bg7 d4 O-O Bf4 d5 Qb3 dxc4 Qxc4 c6 e4 Nbd7 Rd1 Nb6 Qc5 Bg4 Bg5 Na4 Qa3 Nxc3 bxc3 Nxe4 Bxe7 Qb6 Bc4 Nxc3 Bc5 Rfe8+ Kf1".split():
        board.push_san(san)
    assert _sacrificed_pawns(board, board.parse_san("Be6")) == 9 - 3  # Byrne-Fischer 1956: the queen stays en prise to Bc5
    assert _sacrificed_pawns(chess.Board(), chess.Move.from_uci("g1f3")) == 0
    opera = chess.Board("3rkb1r/p2nqppp/5n2/1B2p1B1/4P3/1Q6/PPP2PPP/2KR3R w k - 3 13")
    assert _sacrificed_pawns(opera, opera.parse_san("Rxd7")) == 2  # Morphy's exchange sacrifice


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


def test_mistake_puzzles_come_from_reviews(client):
    assert client.get("/api/puzzles/mistakes").json()["total"] == 0
    # play a game where the player (white) hangs the queen on move 2, then review it
    game = client.post("/api/play/games", json={"bot_id": "sam", "player_color": "white"}).json()
    for mv in ["e2e4", "d1h5", "h5h6"]:
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
    ms = client.get("/api/puzzles/mistakes").json()
    if ms["total"]:
        p = ms["puzzles"][0]
        assert p["solver_first"] and p["moves"] and "myMistake" in p["themes"]
        a = client.post(f"/api/puzzles/{p['id']}/attempt", json={"solved": True, "mode": "mistakes"}).json()
        assert a["delta"] == 0
        assert client.get("/api/puzzles/mistakes").json()["puzzles"][-1]["solved_before"] in (True, False)


def test_fen_import_is_reviewed_from_the_fen(client):
    fen = "8/8/8/3k4/8/8/7Q/4K3 w - - 0 40"
    pgn = f'[SetUp "1"]\n[FEN "{fen}"]\n\n40. Qh5+ Kd4 41. Qe2 Kc3 *'
    r = client.post("/api/review/import", json={"pgn": pgn, "mode": "quick"})
    assert r.status_code == 200, r.text
    rep = _wait(client, r.json()["job"]["id"])["report"]
    assert rep["moves"][0]["fen_before"] == fen
    assert [m["move_number"] for m in rep["moves"]] == [40, 40, 41, 41]
    assert client.get(f"/api/review/games/{r.json()['game_id']}").json()["game"]["start_fen"] == fen


def test_fools_mate_notes_name_the_mate(client):
    r = client.post("/api/review/import", json={"pgn": "1. f3 e5 2. g4 Qh4# 0-1", "mode": "quick"})
    rep = _wait(client, r.json()["job"]["id"])["report"]
    g4, qh4 = rep["moves"][2], rep["moves"][3]
    assert g4["classification"] == C.BLUNDER and "mate in 1" in g4["note"] and "pawns lost" not in g4["note"]
    assert qh4["note"] == "Checkmate."
    assert 3 in rep["key_moments"]


def test_summary_fallback_names_only_errors():
    from backend.routers.coach import _rules_summary
    side = {"accuracy": 80.0, "phase_accuracy": {"opening": 80.0, "middlegame": None, "endgame": None}}
    moves = [{"is_key_moment": True, "color": "white", "move_number": 5, "san": "Nxe5", "classification": C.BRILLIANT,
              "best_move_san": "Nxe5", "win_before": 60.0, "win_after": 60.0}]
    text = _rules_summary({"white": side, "black": side, "opening": None, "moves": moves}, "white")
    assert "was better" not in text and "strongest phase" not in text
