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
    from backend.routers.coach import _unverified_moves, _verified
    facts = {"candidate_moves": [{"move": "e4", "line": ["e4", "e5", "Nf3", "Nc6"]}]}
    verified = _verified(chess.Board(), facts)
    text = "The line 1.e4 e5 2.Nf3 Nc6 is sound. Then 3.Nd5 or 3.e7 would be invented; the pawn on e4 is fine."
    assert _unverified_moves(text, verified) == ["Nd5", "e7"]


def test_a_legal_move_of_the_side_not_to_move_counts_only_when_the_facts_name_it():
    from backend.routers.coach import _unverified_moves, _verified
    board = chess.Board("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")  # 1.e4, Black to move
    text = "White can play Qh5 or Bc4 next."
    assert _unverified_moves(text, _verified(board, {})) == ["Bc4", "Qh5"]
    threat = {"opponent_threat": {"san": "Qh5", "line": ["Qh5"]}}
    assert _unverified_moves(text, _verified(board, threat)) == ["Bc4"]
    assert _unverified_moves(text, _verified(board, {}) | {"Bc4"}) == ["Qh5"]  # a move played earlier in the game


def test_a_legal_move_of_the_previous_position_is_not_verified_in_a_game(client, monkeypatch):
    from backend.routers import coach as R

    async def model(**_):
        yield "White could have played Qh5."
    monkeypatch.setattr(R, "llm_enabled", lambda: True)
    monkeypatch.setattr(R, "stream_text", model)
    game_id = client.post("/api/review/import", json={"pgn": "1. e4 e5 2. Nf3 *", "mode": "quick"}).json()["game_id"]
    board = chess.Board()
    for san in ("e4", "e5", "Nf3"):
        board.push_san(san)
    r = client.post("/api/coach/chat", json={"fen": board.fen(), "question": "What now?", "game_id": game_id})
    assert _events(r.text)[-1]["unverified_moves"] == ["Qh5"]


def test_the_move_just_played_is_verified_without_the_game_list(client):
    from backend.routers import coach as R

    before = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2")
    after = before.copy()
    after.push_san("Qh4")
    answer = R.chat_answer(after, "What now?", level="intermediate",
                           context={"game": {"last_move_uci": "d8h4", "positions": [before.fen(), after.fen()]}})
    _, _, verified = client.portal.call(lambda: answer)
    assert R._unverified_moves("Black just played Qh4, which hangs the queen.", verified) == []


def test_the_context_module_imports_on_its_own():
    import subprocess
    import sys
    r = subprocess.run([sys.executable, "-c", "import backend.coach.context"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_an_unknown_bot_is_no_bot():
    from backend.coach.context import bot_brief
    assert bot_brief("opening-course-that-was-renamed-1200") is None and bot_brief(None) is None
    assert bot_brief("coach")["name"]


def test_fallback_claims_an_ignored_threat_only_when_it_is_still_the_best_reply():
    side = {"hanging_pieces": [], "attackers_near_king": 0, "developed_minors": 2, "king_square": "g1"}
    before = {"candidate_moves": [], "opponent_threat": {"san": "Ng5", "kind": "engine"}}
    after = {"side_to_move": "white", "in_check": False, "white": side, "black": {**side, "king_square": "g8"},
             "candidate_moves": [{"move": "Bd3", "uci": "c4d3", "eval": "+0.40", "line": ["Bd3"]}]}
    kw = dict(move_san="h6", mover="black", classification="inaccuracy", best_san="d6", best_line=["d6"],
              eval_before="+0.10", eval_after="+0.40", level="beginner")
    assert "ignores the threat" not in fallback.explain_move_text(facts_before=before, facts_after=after, **kw)
    still = {**after, "candidate_moves": [{"move": "Ng5", "uci": "f3g5", "eval": "+0.90", "line": ["Ng5"]}]}
    assert "ignores the threat of Ng5" in fallback.explain_move_text(facts_before=before, facts_after=still, **kw)


def test_summary_fallback_invents_nothing_for_an_absent_opening_or_accuracy():
    from backend.routers.coach import _rules_summary
    me = {"accuracy": None, "phase_accuracy": {"opening": None, "middlegame": None, "endgame": None}}
    bot = {"accuracy": 91.0, "phase_accuracy": {}}
    text = _rules_summary({"white": me, "black": bot, "opening": None, "moves": []}, "white")
    assert "None" not in text and "unnamed" not in text.lower() and "unknown" not in text.lower()


RUY_AFTER_CASTLING = "r1bqkb1r/1ppp1ppp/p1n2n2/4p3/B3P3/5N2/PPPP1PPP/RNBQ1RK1 b kq - 5 5"  # 5.O-O, Black to move


def test_a_tried_move_is_judged_with_the_engines_answer_and_the_book_name(client):
    r = client.post("/api/coach/try", json={"fen": RUY_AFTER_CASTLING, "move": "f6e4", "compare": "f8e7"})
    assert r.status_code == 200
    tried, compare = r.json()["tried"], r.json()["compare"]
    assert tried["san"] == "Nxe4" and tried["opening"]["name"] == "Ruy Lopez: Open"
    assert tried["classification"] in ("best", "great", "excellent", "good") and tried["reply_line"]
    assert tried["explanation"].startswith("Nxe4 is ")
    assert tried["reply_text"].startswith("6.") and isinstance(tried["material_after_reply"], int)
    assert compare["san"] == "Be7" and compare["opening"]["name"].startswith("Ruy Lopez")
    assert client.post("/api/coach/try", json={"fen": RUY_AFTER_CASTLING, "move": "e2e4"}).status_code == 400


def test_a_question_names_moves_by_san_or_by_piece_and_square():
    board = chess.Board(RUY_AFTER_CASTLING)
    from backend.routers.coach import asked_moves
    assert [board.san(m) for m in asked_moves(board, "why didn't the knight take e4?")] == ["Nxe4"]
    assert [board.san(m) for m in asked_moves(board, "Why not Nxe4 here?")] == ["Nxe4"]
    assert asked_moves(board, "what is the plan?") == []


def test_chat_answers_a_why_not_question_from_the_judged_move(client):
    r = client.post("/api/coach/chat", json={"fen": RUY_AFTER_CASTLING, "question": "why didn't the knight take e4?"})
    text = "".join(e.get("text", "") for e in _events(r.text) if e["type"] == "text")
    assert text.startswith("Nxe4 is ") and "Ruy Lopez: Open" in text


# ---------------------------------------------------------------- the richer fact sheet: one rule, one position each

def test_fact_rules_read_the_board():
    from backend.coach import facts as F
    # a knight on e5 stands between the b2 bishop and the king on g7: moving it is a discovered check
    d = F.discovered_attacks(chess.Board("8/6k1/8/4N3/8/8/1B6/6K1 w - - 0 1"), chess.WHITE)
    assert d and d[0]["piece"] == "knight on e5" and d[0]["kind"] == "check" and d[0]["moves"]
    # the same with a rook on g7: a discovered attack on a bigger piece
    d = F.discovered_attacks(chess.Board("6k1/5pr1/8/8/3N4/8/1B6/K7 w - - 0 1"), chess.WHITE)
    assert d and d[0]["kind"] == "attack" and "rook on g7" in d[0]["reveals"]
    assert F.discovered_attacks(chess.Board(), chess.WHITE) == []
    # Bxa7?? b6: the bishop is attacked by the rook and every square it can go to loses it
    assert F.unsafe_pieces(chess.Board("r3k3/Bppp4/1p6/8/8/8/8/4K3 w - - 0 1"), chess.WHITE) == (["bishop on a7"], [])
    assert F.unsafe_pieces(chess.Board(), chess.WHITE) == ([], [])
    # in check from b4 the rook on a1 cannot move, but it has free squares once the check is answered
    assert F.unsafe_pieces(chess.Board("4k3/8/8/8/1b6/1n6/8/R3K3 w - - 0 1"), chess.WHITE) == ([], [])
    # a fianchetto without the bishop: f3, g2 and h3 can never be guarded by a pawn; Black's cover is intact
    b = chess.Board("6k1/5ppp/8/8/8/6P1/5P1P/6K1 w - - 0 1")
    assert F.holes_near_king(b, chess.WHITE) == ["f3", "g2", "h3"] and F.holes_near_king(b, chess.BLACK) == []
    # a knight on d5 guarded by e4 with no black c- or e-pawn left
    assert F.outposts(chess.Board("r1bq1rk1/pp3pbp/6p1/3N4/4P3/8/PP3PPP/R2QKB1R w KQ - 0 1"), chess.WHITE) == ["d5"]
    # c4-c5 hits d6 and f2-f4 hits e5; for Black, d6-d5 hits c4 and e4
    b = chess.Board("rnbqkb1r/ppp2ppp/3p1n2/4p3/2PPP3/2N5/PP3PPP/R1BQKBNR w KQkq - 0 4")
    assert {"c5", "f4"} <= set(F.pawn_breaks(b, chess.WHITE)) and "d5" in F.pawn_breaks(b, chess.BLACK)
    files = F.file_facts(chess.Board("r4rk1/pp3ppp/2p5/8/8/2P5/PP3PPP/3R1RK1 w - - 0 1"))
    assert files["open"] == ["d", "e"] and files["rooks_or_queens_on"] == {"d": "white"}
    assert F.file_facts(chess.Board("rnbqkbnr/pppppppp/8/8/8/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1"))["half_open"] == {"white": ["e"], "black": []}
    assert F.eval_trend([50, 52, 55, 61, 70, 72, 80])["direction"] == "white gaining"
    assert F.eval_trend([50, 51])["direction"] == "steady" and F.eval_trend([50]) is None
    book = F.book_line(chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"))
    assert book["main_line"][:2] == ["Nc6", "Bb5"] and book["leads_to"].startswith("Ruy Lopez")
    assert F.book_line(chess.Board("8/8/4k3/8/3K4/3P4/8/8 w - - 0 1")) is None
    assert F.endgame_rule(chess.Board("8/8/4k3/8/3K4/3P4/8/8 w - - 0 1"))["kind"] == "pawn"
    assert F.endgame_rule(chess.Board("6k1/8/8/3P4/8/8/r7/4R1K1 w - - 0 1"))["kind"] == "rook"
    assert F.endgame_rule(chess.Board("8/8/4k3/8/3K4/3P4/8/2B2b2 w - - 0 1"))["kind"] == "opposite bishops"
    assert F.endgame_rule(chess.Board()) is None
    for pawnless in ("7k/8/8/8/8/8/8/K7 w - - 0 1", "7k/8/8/8/8/8/8/KR6 w - - 0 1"):  # bare kings, KR v K: no pawn rule
        assert F.endgame_rule(chess.Board(pawnless)) is None


def test_the_sheet_says_what_the_last_move_did_and_what_the_opponent_threatens(event_loop):
    async def run():
        pool = EnginePool()
        await pool.start()
        try:
            before = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
            after = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2")
            f = await position_facts(after, pool, depth=8, last_move=chess.Move.from_uci("g1f3"), previous_fen=before.fen())
            assert "develops the knight" in f["last_move"]["purpose"] and "attacks the pawn on e5" in f["last_move"]["purpose"]
            assert f["opponent_threat"]["san"] == "Nxe5"
            assert f["assessment"]["verdict"] and f["assessment"]["plans"]["Black"] and f["phase_goal"]
            assert f["book"]["main_line"] and f["files"]["open"] == []
            assert f["candidate_moves"][0]["does"]
            scholar = await position_facts(chess.Board("r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3"), pool, depth=8)
            assert scholar["opponent_threat"]["san"] == "Qxf7#" and scholar["opponent_threat"]["kind"] == "mate"
        finally:
            await pool.stop()

    event_loop.run_until_complete(run())


# ---------------------------------------------------------------- the coach knows the player and the game

def test_the_level_comes_from_the_puzzle_rating_and_beginners_get_beginner_wording():
    from backend.coach.context import level_for_band
    from backend.routers.coach import level_of
    assert [level_for_band(b) for b in (1, 2, 3, 5, 7, 8)] == ["beginner", "beginner", "intermediate", "advanced", "master", "master"]
    assert level_of(None, {"player": {"level": "beginner"}}) == "beginner"
    assert level_of("master", {"player": {"level": "beginner"}}) == "master"
    assert level_of(None, {"player": {"level": None}}) == "intermediate"
    facts = {
        "side_to_move": "white", "phase": "middlegame", "in_check": False, "opening": None,
        "white": {"hanging_pieces": [], "attackers_near_king": 0, "developed_minors": 3, "king_square": "g1"},
        "black": {"hanging_pieces": ["knight on e5"], "attackers_near_king": 1, "developed_minors": 2, "king_square": "g8"},
        "assessment": {"verdict": "White is slightly better: White's pieces are more active.", "imbalances": [], "plans": {"White": ["keep the initiative: make a threat with every move"], "Black": []}},
        "candidate_moves": [{"move": "Nxe5", "uci": "f3e5", "eval": "+2.10", "line": ["Nxe5", "d6", "Nf3", "Nc6"], "does": ["takes the knight on e5 for free"]}],
        "threats_against_side_to_move": [], "opponent_threat": {"san": "Nxf3", "reason": "wins the knight for the knight"},
    }
    beginner = fallback.chat_text(facts, "what should I play?", "beginner")
    intermediate = fallback.chat_text(facts, "what should I play?", "intermediate")
    assert "+2.10" not in beginner and "slightly better" not in beginner and "Nxe5 d6 Nf3 Nc6" not in beginner
    assert "+2.10" in intermediate and "slightly better" in intermediate and "Nxe5 d6 Nf3 Nc6" in intermediate
    for text in (beginner, intermediate):  # the structure is the same: check, suggestion, plan, question
        assert "what your opponent wants: Nxf3" in text and "engine prefers Nxe5" in text and "Your plan: keep the initiative" in text and text.endswith("?")


def _wait_for_review(client, job_id: str) -> None:
    for _ in range(150):
        if client.get(f"/api/review/jobs/{job_id}").json()["status"] == "done":
            return
        time.sleep(0.2)
    raise AssertionError("review did not finish")


BLUNDER_PGN = ('[White "A"]\n[Black "B"]\n[Result "*"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 5. d3 d6 6. O-O O-O 7. Bg5 h6 '
               '8. Bh4 Be6 9. Bxe6 fxe6 10. Nbd2 Qe8 11. Qe2 g5 12. Nxg5 hxg5 *')  # 12.Nxg5?? gives a knight for a pawn


def test_a_question_in_a_game_knows_the_moves_so_far_and_the_earlier_blunder(client):
    imp = client.post("/api/review/import", json={"pgn": BLUNDER_PGN, "mode": "quick"}).json()
    _wait_for_review(client, imp["job"]["id"])
    report = client.get(f"/api/review/games/{imp['game_id']}").json()["report"]
    assert report["moves"][22]["san"] == "Nxg5" and report["moves"][22]["classification"] in ("mistake", "blunder")
    board = chess.Board()
    for m in report["moves"]:
        board.push_uci(m["uci"])
    r = client.post("/api/coach/chat", json={"fen": board.fen(), "question": "What should I play now?", "game_id": imp["game_id"]})
    assert r.status_code == 200
    text = "".join(e.get("text", "") for e in _events(r.text) if e["type"] == "text")
    assert "move 12 Nxg5 was a" in text and "the same check applies now" not in text and "was a inaccuracy" not in text
    assert "Your opponent's hxg5" in text  # the last move and its purpose come from the game, not from the FEN
    assert client.post("/api/coach/chat", json={"fen": board.fen(), "question": "x", "game_id": "nope"}).status_code == 404
    assert client.post("/api/coach/chat", json={"fen": board.fen(), "question": "x", "lesson_id": "nope"}).status_code == 404


def test_game_context_cuts_the_moves_at_the_position_on_the_board(event_loop):
    import backend.coach.context as ctx

    moves = []
    b = chess.Board()
    for san in ("e4", "e5", "Nf3", "Nc6"):
        mv = b.parse_san(san)
        b.push(mv)
        moves.append({"san": san, "uci": mv.uci(), "fen": b.fen()})
    row = {"moves": moves, "player_color": "white", "bot_id": "coach", "time_control": "5+0", "start_fen": None}
    report = {"moves": [{"color": c, "classification": "book", "move_number": 1 + i // 2, "san": m["san"], "best_move_san": m["san"]}
                        for i, (c, m) in enumerate(zip(("white", "black") * 2, moves))], "eval_graph": [50, 51, 50, 52, 51]}

    async def read_game(player, game_id):
        return row

    async def stored_report(player, game_id):
        return report

    orig = ctx.store.read_game, ctx.stored_report
    ctx.store.read_game, ctx.stored_report = read_game, stored_report
    try:
        after_two = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
        g = event_loop.run_until_complete(ctx.game_context("p", "g", after_two))
        assert g["moves_so_far"] == "1.e4 e5" and g["last_move_uci"] == "e7e5" and g["positions"][-2].startswith("rnbqkbnr/pppppppp/8/8/4P3")
        assert g["played"] == ["e4", "e5"]
        assert event_loop.run_until_complete(ctx.game_context("p", "g", chess.Board(), ply=3))["moves_so_far"] == "1.e4 e5 2.Nf3"
        assert g["bot"]["name"] and g["time_control"] == "5+0" and g["eval_trend"]["win_percent_white"] == [50, 51, 50]
        g = event_loop.run_until_complete(ctx.game_context("p", "g", chess.Board()))
        assert g["moves_so_far"] == "" and g["last_move_uci"] is None
        off_line = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/3PP3/8/PPP2PPP/RNBQKBNR b KQkq - 0 2")  # 2.d4 was never played
        g = event_loop.run_until_complete(ctx.game_context("p", "g", off_line))
        assert g["moves_so_far"] == "1.e4 e5 2.Nf3 Nc6" and g["last_move_uci"] is None
    finally:
        ctx.store.read_game, ctx.stored_report = orig


def test_a_repeated_position_counts_at_its_last_occurrence(event_loop):
    import backend.coach.context as ctx

    moves, b = [], chess.Board()
    for san in ("Nf3", "Nf6", "Ng1", "Ng8", "Nf3", "Nf6"):
        mv = b.parse_san(san)
        b.push(mv)
        moves.append({"san": san, "uci": mv.uci(), "fen": b.fen()})
    row = {"moves": moves, "player_color": "white", "bot_id": None, "time_control": None, "start_fen": None}

    async def read_game(player, game_id):
        return row

    async def stored_report(player, game_id):
        return None

    orig = ctx.store.read_game, ctx.stored_report
    ctx.store.read_game, ctx.stored_report = read_game, stored_report
    try:
        g = event_loop.run_until_complete(ctx.game_context("p", "g", b))
        assert g["moves_so_far"] == "1.Nf3 Nf6 2.Ng1 Ng8 3.Nf3 Nf6" and g["bot"] is None
        back_home = event_loop.run_until_complete(ctx.game_context("p", "g", chess.Board()))
        assert back_home["moves_so_far"] == "1.Nf3 Nf6 2.Ng1 Ng8"  # not cut to the empty start
    finally:
        ctx.store.read_game, ctx.stored_report = orig


def test_the_sheet_names_the_drawing_resource_of_the_side_behind():
    from backend.coach.facts import drawing_resource, endgame_rule

    def top(move: str, line: list[str]) -> list[dict]:
        return [{"move": move, "line": line}]
    perpetual = chess.Board("6k1/R4ppp/R7/1P6/P7/7P/5PPK/2q5 b - - 0 1")  # Black is 3 pawns down
    d = drawing_resource(perpetual, top("Qf4+", ["Qf4+", "Kg1", "Qc1+", "Kh2"]), 0, 3, None)
    assert d["kind"] == "perpetual check" and d["move"] == "Qf4+"
    assert drawing_resource(perpetual, top("Qf4+", ["Qf4+", "Kg1", "Qc1+", "Kh2"]), 250, 3, None) is None  # the engine says White wins
    assert drawing_resource(perpetual, top("h6", ["h6", "Rb7"]), 0, 3, None) is None  # a draw with no named resource
    stalemate = chess.Board("7k/5Q2/6KP/8/8/8/8/r7 b - - 0 1")  # the king has no move: only the rook moves
    assert drawing_resource(stalemate, top("Rg1+", ["Rg1+"]), 0, 5, None)["kind"] == "stalemate"
    wrong = chess.Board("8/5k2/8/8/4K2P/3B4/8/8 b - - 0 1")  # a light bishop cannot cover h8
    assert endgame_rule(wrong)["kind"] == "wrong bishop"
    assert drawing_resource(wrong, top("Kg7", ["Kg7"]), 0, 4, endgame_rule(wrong))["kind"] == "wrong bishop"
    assert endgame_rule(chess.Board("8/5k2/8/8/4K2P/2B5/8/8 b - - 0 1"))["kind"] == "minor piece"  # a dark bishop covers h8


def test_the_fallback_leads_a_losing_answer_with_the_draw():
    facts = {"side_to_move": "black", "material_balance_white": 3, "black": {}, "white": {},
             "drawing_resource": {"kind": "perpetual check", "move": "Qf4+", "text": "Qf4+ Kg1 Qc1+ Kh2 repeats the position"},
             "candidate_moves": [{"move": "Qf4+", "uci": "c1f4", "eval": "+0.00", "line": ["Qf4+", "Kg1", "Qc1+", "Kh2"], "does": ["gives check"]}]}
    assert "3 pawns down, but the engine finds a draw with Qf4+ by perpetual check" in fallback.chat_text(facts, "what now?", "intermediate")
    assert fallback.hint_text(facts, 1) == "You are behind in material: look for the draw (perpetual check)."


def test_the_fallback_names_stalemate_only_when_the_engine_line_ends_in_it():
    fen = "7k/5Q2/6KP/8/8/8/8/r7 b - - 0 1"  # Black's king has no move; without the rook it is stalemate
    trick = {"kind": "stalemate", "move": "Rg1+", "text": "your king has no legal move, so without the rook it is stalemate"}

    def facts(line: list[str]) -> dict:
        return {"fen": fen, "side_to_move": "black", "material_balance_white": 5, "drawing_resource": trick,
                "candidate_moves": [{"move": line[0], "eval": "0.00", "line": line}]}
    checks = fallback.drawing_text(facts(["Rg1+", "Kh5", "Rh1+", "Kg4", "Rg1+"]))  # the rook checks on: no stalemate yet
    assert checks == ("You are 5 pawns down, but the engine finds a draw with Rg1+. A stalemate trick is available: "
                      "your king has no legal move, so without the rook it is stalemate.")
    assert "by stalemate" in fallback.drawing_text(facts(["Ra8", "Qe6", "Ra2", "Qxa2"]))  # the line ends in stalemate


def test_fallback_wording_and_board_facts_name_only_what_is_there():
    from backend.coach.facts import _side_facts
    threat = {"side_to_move": "black", "black": {}, "white": {}, "opponent_threat": {"san": "Qg7#", "reason": "checkmate"}}
    assert fallback.check_first(threat) == "Before you move, see what your opponent wants: Qg7#: it gives checkmate."
    # opposite bishops: the black bishop and king stand near White's king on d5; kings are not counted
    assert _side_facts(chess.Board("8/4k3/8/3KP3/2B5/8/5b2/8 b - - 0 1"), chess.WHITE).attackers_near_king == 1
    bare = chess.Board("8/5k2/8/8/4K2P/3B4/8/8 b - - 0 1")  # no rook or queen: an open file is nothing to either side
    assert _side_facts(bare, chess.WHITE).open_files_for_rooks == [] == _side_facts(bare, chess.BLACK).open_files_for_rooks
    rook = {"side_to_move": "black", "phase": "endgame", "white": {}, "black": {"pieces": {"rook": 1}},
            "files": {"open": ["b"], "rooks_or_queens_on": {}}}
    assert "b-file" not in fallback.plan_text(rook, "intermediate")  # in an endgame the endgame rule speaks
    assert "The b-file is open" in fallback.plan_text({**rook, "phase": "middlegame"}, "intermediate")
