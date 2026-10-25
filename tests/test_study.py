"""The study: rule-based reasons for a move, the engine's why-not stories, the position assessment,
and the missed-puzzle ladder derived from attempts."""
from __future__ import annotations

import asyncio
import io

import chess
import chess.pgn
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.study import annotate as A
from backend.study.assess import imbalances, plans_from, verdict
from backend.study.reasons import forcing_gains, move_reasons, parried_threat
from backend.storage.db import database


def reasons(fen: str, san: str) -> list[str]:
    b = chess.Board(fen)
    return move_reasons(b, b.parse_san(san))


def test_move_reasons_name_what_the_move_does():
    assert reasons("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3", "Bc4") == ["develops the bishop"]
    assert "forks the king and the queen on c8" in " ".join(reasons("2q3k1/8/8/5N2/6P1/7K/8/8 w - - 0 1", "Ne7+")) or reasons("2q3k1/8/8/5N2/6P1/7K/8/8 w - - 0 1", "Ne7+")[0] == "gives check"
    r = reasons("2q3k1/8/8/5N2/6P1/7K/8/8 w - - 0 1", "Ne7+")
    assert "gives check" in r and any("queen on c8" in x for x in r)
    assert reasons("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1", "Ra8#") == ["checkmate"]
    assert reasons("6k1/5p1p/2r3b1/4N3/8/8/5PPP/6K1 w - - 0 1", "Nxc6") == ["takes the rook on c6 for free"]
    assert reasons("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", "e4") == ["takes space in the centre"]
    assert "castles: the king is safe and the rook comes into play" in reasons("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQkq - 0 5", "O-O")
    assert any(x.startswith("pins the knight on c6") for x in reasons("r1bqkbnr/ppp2ppp/2np4/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 4", "Bb5"))
    assert not any(x.startswith("pins") for x in reasons("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3", "Bb5"))  # the d7 pawn shields the king


def test_a_parried_threat_is_named_and_a_check_suffix_does_not_fake_one():
    b = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2")  # 1.e4 e5 2.Nf3: e5 hangs
    assert forcing_gains(chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 1 2"))[0]["san"] == "Nxe5"
    assert parried_threat(b, b.parse_san("Nc6"))["san"] == "Nxe5"
    assert parried_threat(b, b.parse_san("a6")) is None
    # castling out of a check-giving capture: Nxc2+ becomes Nxc2 but the pawn still hangs, so nothing was parried
    b = chess.Board("r1bq1b1r/pp2kppp/2p5/8/1nB5/2N2Q2/PPPP1PPP/R1B1K2R w KQ - 2 10")
    assert parried_threat(b, b.parse_san("O-O")) is None


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    monkeypatch.setattr(A, "STUDY_DIR", tmp_path / "study")
    with TestClient(create_app()) as c:
        yield c


def _study(client, path: str) -> dict:
    """Polls a study endpoint until the engine has worked through the game (the job runs on the app's loop)."""
    for _ in range(600):
        r = client.get(path).json()
        if r["status"] == "done":
            return r["study"]
        assert r["status"] == "running", r
        asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.2))
    raise AssertionError(f"study of {path} did not finish")


def test_the_study_explains_a_blunder_and_offers_the_better_move(client):
    lesson = client.get("/api/learn/lessons/b1m4l3").json()  # Scholar's mate
    idx = next(i for i, s in enumerate(lesson["sections"]) if s["type"] == "game")
    doc = _study(client, f"/api/study/lesson/b1m4l3/{idx}")
    plies = doc["plies"]
    assert [p["san"] for p in plies] == ["e4", "e5", "Qh5", "Nc6", "Bc4", "Nf6", "Qxf7#"]
    nf6 = plies[5]
    assert nf6["classification"] == "blunder" and nf6["problem"] == "Qxf7# is checkmate"
    assert "Better was" in nf6["say"] and any(c["why_not"] is None and not c["played"] for c in nf6["candidates"])
    assert plies[6]["reasons"] == ["checkmate"] and plies[6]["eval_after"] == "#"
    assert plies[4]["threat"] is None or "swing" in plies[4]["threat"]
    for p in plies:
        assert len(p["candidates"]) <= doc["candidates"] and all(c["line"][0] == c["san"] for c in p["candidates"])


def test_a_lesson_game_study_is_computed_once_then_served_from_the_cache(client):
    lesson = client.get("/api/learn/lessons/b1m4l4").json()
    idx = next(i for i, s in enumerate(lesson["sections"]) if s["type"] == "game")
    study = _study(client, f"/api/study/lesson/b1m4l4/{idx}")
    assert [p["san"] for p in study["plies"]] == ["f3", "e5", "g4", "Qh4#"]
    assert study["plies"][2]["classification"] == "blunder"
    assert client.get(f"/api/study/lesson/b1m4l4/{idx}").json()["status"] == "done"  # served from the cache now
    assert list((A.STUDY_DIR).glob("*.json"))
    assert client.get("/api/study/lesson/b1m4l4/0").status_code == 404
    assert client.get("/api/study/game/nope").status_code == 404


def test_the_assessment_names_imbalances_and_plans(client):
    items = imbalances(chess.Board("r1bq1rk1/pp3ppp/2n1p3/3pP3/2pP4/P1P2N2/2P2PPP/R1BQ1RK1 w - - 0 11"))
    kinds = {i["kind"] for i in items}
    assert "passed pawn" not in kinds and "doubled pawns" in kinds and "open file" not in kinds
    assert verdict(10, []) == "The position is level." and verdict(-250, [{"side": "Black", "text": "Black has the bishop pair"}]) == "Black is clearly better: Black has the bishop pair."
    r = client.get("/api/study/assess", params={"fen": "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"}).json()
    assert r["verdict"].startswith("White is winning") and r["plans"]["White"]
    assert client.get("/api/study/assess", params={"fen": "bad"}).status_code == 400


def test_missed_puzzles_come_back_on_the_ladder(client):
    p = client.get("/api/puzzles/next").json()["puzzle"]
    assert client.get("/api/puzzles/review").json() == {"puzzles": [], "due": 0, "later": 0}
    client.post(f"/api/puzzles/{p['id']}/attempt", json={"moves": [], "mode": "rated"})  # a miss
    r = client.get("/api/puzzles/review").json()
    assert r["due"] == 0 and r["later"] == 1  # due tomorrow
    player = client.cookies["player"]
    asyncio.get_event_loop().run_until_complete(database.execute("UPDATE puzzle_attempts SET created_at = datetime('now', '-2 days') WHERE player_id = ?", (player,)))
    r = client.get("/api/puzzles/review").json()
    assert r["due"] == 1 and r["puzzles"][0]["id"] == p["id"]
    assert client.get("/api/learn/curriculum").json()["review_due"] == 1
    client.post(f"/api/puzzles/{p['id']}/attempt", json={"moves": p["moves"][1:], "mode": "review"})  # solved at review: next rung is three days
    assert client.get("/api/puzzles/review").json() == {"puzzles": [], "due": 0, "later": 1}


def test_my_own_game_is_studied_for_me_only(client):
    r = client.post("/api/review/import", json={"pgn": "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0", "mode": "quick"})
    game_id = r.json()["game_id"]
    assert _study(client, f"/api/study/mine/{game_id}")["plies"][5]["classification"] == "blunder"
    assert list((A.STUDY_DIR / "mine").glob("*.json")) and not list(A.STUDY_DIR.glob("*.json"))  # never the committed folder
    client.cookies.clear()  # another player cannot study it
    assert client.get(f"/api/study/mine/{game_id}").status_code == 404


def test_the_side_behind_gets_no_plan_that_needs_pieces_it_does_not_have():
    def plan_of_black(fen: str) -> str:
        return next(i["plan_against"] for i in imbalances(chess.Board(fen)) if i["kind"] == "material")
    assert plan_of_black("8/5k2/8/8/4K2P/3B4/8/8 b - - 0 1") == "put your king in front of White's pawns"  # a bare king
    assert plan_of_black("8/4k3/8/3KP3/2B5/8/5b2/8 b - - 0 1") == "put your king in front of White's pawns and trade pawns, not pieces"
    assert plan_of_black("7k/8/8/8/8/8/8/3QK3 b - - 0 1") == "keep your king off the edge, where mates happen"
    assert "make threats" in plan_of_black("6k1/R4ppp/R7/1P6/P7/7P/5PPK/2q5 b - - 0 1")  # the queen can check


def test_no_plan_names_a_piece_the_side_does_not_have():
    for fen in ("8/5k2/8/8/4K2P/3B4/8/8 b - - 0 1", "8/8/8/4k3/8/8/4P3/4K3 w - - 0 1"):  # wrong bishop; K+P v K
        plans = plans_from(imbalances(chess.Board(fen)), "endgame")
        black = " ".join(plans["Black"])  # a bare king: no knight, bishop, rook, queen or piece to name
        assert not any(w in black for w in ("knight", "bishop", "rook", "queen", "with a piece", "pieces")), plans["Black"]
        assert "put your king on the square in front of it" in plans["Black"]
    assert not any(i["kind"] == "open file" for i in imbalances(chess.Board("7k/5Q2/6KP/8/8/8/8/r7 b - - 0 1")))  # an endgame


def test_plans_name_only_pieces_the_side_has():
    from backend.study.assess import imbalances

    def plans(fen, kind):
        return [(i["plan_for"], i["plan_against"]) for i in imbalances(chess.Board(fen)) if i["kind"] == kind]
    # White has one rook: no "double rooks"
    assert all("double" not in p for p, _ in plans("2Q2bk1/5p1p/p5p1/2p3P1/2r1B3/7P/qPQ2P2/2K4R b - - 0 1", "open file"))
    # Black has no queen: no "keep the queens on"
    assert all("queens" not in a for _, a in plans("1k1r3r/1b1p1p2/p3p3/1p2Pn2/3n2Np/P1Q5/1P3PPP/1B2NRK1 w - - 0 1", "weak king cover"))
    # White has only king and pawns: the answer to the knight outpost names the king
    assert plans("8/8/7K/P4k2/8/6p1/5nP1/8 b - - 0 1", "outpost") == [("build around it: it ties the opponent down", "keep your king off the squares it attacks")]
