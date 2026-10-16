"""Coach: the fact sheet is right about the board, and the rule-based path answers without a key."""
from __future__ import annotations

import json
import time

import chess
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.coach import fallback
from backend.coach.facts import position_facts
from backend.engine.pool import EnginePool


def test_facts_describe_the_board(event_loop):
    async def run():
        pool = EnginePool()
        await pool.start()
        try:
            # White queen on h5 attacks f7; black's knight on c6 is pinned? no - simple hanging test
            board = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3")
            f = await position_facts(board, pool, depth=8)
            assert f["side_to_move"] == "black"
            assert f["phase"] == "opening"
            assert f["candidate_moves"] and f["candidate_moves"][0]["move"]
            assert any(t["san"] == "Qxf7#" for t in f["threats_against_side_to_move"])
            hang = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2")
            hang.push_san("Qh4")  # queen hangs to Nxh4
            f2 = await position_facts(hang, pool, depth=8)
            assert "queen on h4" in f2["black"]["hanging_pieces"]
        finally:
            await pool.stop()

    event_loop.run_until_complete(run())


def test_fallback_texts_are_grounded():
    facts = {
        "side_to_move": "white", "phase": "middlegame", "in_check": False, "opening": None,
        "white": {"hanging_pieces": [], "attackers_near_king": 0, "developed_minors": 3, "king_square": "g1"},
        "black": {"hanging_pieces": ["knight on e5"], "attackers_near_king": 1, "developed_minors": 2, "king_square": "g8"},
        "candidate_moves": [{"move": "Nxe5", "uci": "f3e5", "eval": "+2.10", "line": ["Nxe5", "d6", "Nf3"]}],
        "threats_against_side_to_move": [],
    }
    t = fallback.explain_move_text(move_san="Bd3", mover="white", classification="mistake", best_san="Nxe5", best_line=["Nxe5", "d6"],
                                   eval_before="+2.10", eval_after="+0.30", facts_before=facts, facts_after=facts, level="beginner")
    assert "Bd3 is a mistake" in t and "Nxe5" in t
    assert "Nxe5" in fallback.chat_text(facts, "what should I play?", "beginner")
    assert "loose piece" in fallback.hint_text(facts, 1)
    assert "f3" in fallback.hint_text(facts, 2)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    monkeypatch.setattr(s.settings, "ANTHROPIC_API_KEY", "")
    with TestClient(create_app()) as c:
        yield c


def _events(text: str) -> list[dict]:
    return [json.loads(l[5:]) for l in text.split("\n") if l.startswith("data:")]


def test_coach_endpoints_fall_back_to_rules(client):
    fen = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3"
    r = client.post("/api/coach/hint", json={"fen": fen, "hint_level": 1})
    assert r.status_code == 200
    ev = _events(r.text)
    assert ev[-1]["type"] == "done" and ev[-1]["source"] == "rules"
    assert any(e["type"] == "text" for e in ev)
    r = client.post("/api/coach/chat", json={"fen": fen, "question": "What should I play?"})
    assert "engine prefers" in r.text
    assert client.post("/api/coach/chat", json={"fen": "not a fen", "question": "x"}).status_code == 400

    pgn = '[White "A"]\n[Black "B"]\n[Result "1-0"]\n\n1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0'
    imp = client.post("/api/review/import", json={"pgn": pgn, "mode": "quick"}).json()
    for _ in range(100):
        j = client.get(f"/api/review/jobs/{imp['job']['id']}").json()
        if j["status"] == "done":
            break
        time.sleep(0.2)
    r = client.post("/api/coach/explain", json={"game_id": imp["game_id"], "ply": 6, "level": "beginner"})
    ev = _events(r.text)
    text = "".join(e.get("text", "") for e in ev if e["type"] == "text")
    assert "Nf6 is a blunder" in text and "Better was" in text
    r = client.post("/api/coach/summary", json={"game_id": imp["game_id"]})
    assert "accuracy" in r.text


def test_a_position_without_a_king_is_refused_and_the_engine_survives(client):
    assert client.get("/api/coach/facts", params={"fen": "8/8/8/8/8/8/8/KR6 w - - 0 1"}).status_code == 400
    assert client.get("/api/coach/facts", params={"fen": chess.STARTING_FEN}).status_code == 200


def test_fallback_names_the_opponents_reply_not_the_movers_threat():
    side = {"hanging_pieces": [], "attackers_near_king": 0, "developed_minors": 2, "king_square": "g1"}
    after = {"side_to_move": "black", "in_check": False, "white": side, "black": {**side, "king_square": "g8"},
             "candidate_moves": [{"move": "Qb6", "uci": "d8b6", "eval": "-1.20", "line": ["Qb6"]}],
             "threats_against_side_to_move": [{"san": "Qxa1"}]}  # white's own threat after white's move
    t = fallback.explain_move_text(move_san="Ne7", mover="white", classification="inaccuracy", best_san="Nf3", best_line=["Nf3"],
                                   eval_before="+0.30", eval_after="-0.40", facts_before=after, facts_after=after, level="beginner")
    assert "Qxa1" not in t and "Qb6" in t


def test_fallback_names_an_allowed_mate_before_a_hanging_piece():
    # Legal's mate: 5...Bxd1?? takes the queen and allows Bxf7+ Ke7 Nd5#; the bishop on d1 is beside the point
    white = {"hanging_pieces": [], "attackers_near_king": 0, "developed_minors": 3, "king_square": "e1"}
    black = {"hanging_pieces": ["bishop on d1"], "attackers_near_king": 2, "developed_minors": 1, "king_square": "e8"}
    after = {"side_to_move": "white", "in_check": False, "phase": "opening", "white": white, "black": black, "evaluation": "M2",
             "candidate_moves": [{"move": "Bxf7+", "uci": "c4f7", "eval": "M2", "line": ["Bxf7+", "Ke7", "Nd5#"]}],
             "threats_against_side_to_move": []}
    t = fallback.explain_move_text(move_san="Bxd1", mover="black", classification="blunder", best_san="dxe5", best_line=["dxe5"],
                                   eval_before="+1.20", eval_after="M2", facts_before=after, facts_after=after, level="beginner")
    assert t.startswith("Bxd1 is a blunder. This allows mate in 2: Bxf7+ Ke7 Nd5#.")
    assert "hanging" not in t and "for free" not in t
    white_moved = {**after, "side_to_move": "black", "evaluation": "-M2"}
    assert "allows mate" not in fallback.explain_move_text(
        move_san="Bxd1", mover="black", classification="blunder", best_san="dxe5", best_line=[], eval_before="+1.20",
        eval_after="-M2", facts_before=white_moved, facts_after=white_moved, level="beginner")  # black's own mate is not allowed


def test_unverified_moves_knows_the_fact_sheet_lines_and_numbered_pawn_moves():
    from backend.routers.coach import _unverified_moves, _with_lines
    facts = {"candidate_moves": [{"move": "e4", "line": ["e4", "e5", "Nf3", "Nc6"]}]}
    boards = _with_lines(chess.Board(), facts)
    text = "The line 1.e4 e5 2.Nf3 Nc6 is sound. Then 3.Nd5 or 3.e7 would be invented; the pawn on e4 is fine."
    assert _unverified_moves(text, boards) == ["Nd5", "e7"]


def test_summary_fallback_invents_nothing_for_an_absent_opening_or_accuracy():
    from backend.routers.coach import _rules_summary
    me = {"accuracy": None, "phase_accuracy": {"opening": None, "middlegame": None, "endgame": None}}
    bot = {"accuracy": 91.0, "phase_accuracy": {}}
    text = _rules_summary({"white": me, "black": bot, "opening": None, "moves": []}, "white")
    assert "None" not in text and "unnamed" not in text.lower() and "unknown" not in text.lower()
