"""Play API: a full game loop against a weak bot through the HTTP layer."""
from __future__ import annotations

import random

import chess
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.bots.roster import BOTS, get_bot
from backend.bots.selector import choose_move
from backend.engine.pool import EnginePool


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    with TestClient(create_app()) as c:
        yield c


def test_roster_is_consistent():
    ids = [b.id for b in BOTS]
    assert len(ids) == len(set(ids))
    elos = [b.elo for b in BOTS if b.tier != "special"]
    assert elos == sorted(elos)
    assert get_bot("stockfish").selection.temperature_cp == 0


def test_bots_endpoint(client):
    r = client.get("/api/bots")
    assert r.status_code == 200
    names = {b["name"] for b in r.json()["bots"]}
    assert {"Pip", "Stockfish", "Coach"} <= names


def test_game_loop_against_pip(client):
    r = client.post("/api/play/games", json={"bot_id": "pip", "player_color": "white"})
    assert r.status_code == 200, r.text
    game = r.json()
    assert game["turn"] == "w" and game["status"] == "active" and "e2e4" in game["legal_moves"]

    board = chess.Board()
    plies = 0
    while game["status"] == "active" and plies < 30:
        mv = random.choice(list(board.legal_moves))
        r = client.post(f"/api/play/games/{game['id']}/move", json={"move": mv.uci()})
        assert r.status_code == 200, r.text
        body = r.json()
        game = body["game"]
        board = chess.Board(game["fen"])
        assert body["player_move"]["uci"] == mv.uci()
        if game["status"] == "active":
            assert body["bot_move"] is not None
            assert body["bot_move"]["by"] == "bot"
        plies += 1
    assert plies > 0

    r = client.get(f"/api/play/games/{game['id']}")
    assert r.status_code == 200
    assert len(r.json()["moves"]) == len(game["moves"])
    assert "1. " in r.json()["pgn"]
    assert client.get("/api/play/games").json()["games"][0]["id"] == game["id"]


def test_illegal_and_wrong_turn_are_rejected(client):
    game = client.post("/api/play/games", json={"bot_id": "luna", "player_color": "white"}).json()
    assert client.post(f"/api/play/games/{game['id']}/move", json={"move": "e2e5"}).status_code == 400
    assert client.post(f"/api/play/games/{game['id']}/move", json={"move": "zzz"}).status_code == 400
    assert client.post(f"/api/play/games/{game['id']}/move", json={"move": "Nf3"}).status_code == 200


def test_black_gets_first_bot_move_and_hint_and_takeback(client):
    game = client.post("/api/play/games", json={"bot_id": "sam", "player_color": "black"}).json()
    assert game["turn"] == "b" and len(game["moves"]) == 1 and game["moves"][0]["by"] == "bot"
    h = client.get(f"/api/play/games/{game['id']}/hint").json()
    assert h["move_uci"] in game["legal_moves"]
    assert h["line_san"][0] == h["move_san"]
    r = client.post(f"/api/play/games/{game['id']}/move", json={"move": h["move_uci"], "want_eval": True}).json()
    assert r["eval_text"] is not None
    assert len(r["game"]["moves"]) == 3
    tb = client.post(f"/api/play/games/{game['id']}/takeback").json()
    assert len(tb["moves"]) == 1
    rs = client.post(f"/api/play/games/{game['id']}/resign").json()
    assert rs["status"] == "finished" and rs["result"] == "1-0"


def test_selector_strength_ladder(event_loop):
    """A master bot picks the engine's best line; Pip wanders. Measured on one tactical position."""
    async def run():
        pool = EnginePool()
        await pool.start()
        try:
            board = chess.Board("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4")
            rng = random.Random(1)
            master = [(await choose_move(board, get_bot("elena"), pool, rng)).move for _ in range(3)]
            assert all(m == chess.Move.from_uci("h5f7") for m in master)
            pip_moves = {(await choose_move(board, get_bot("pip"), pool, rng)).move for _ in range(12)}
            assert len(pip_moves) > 1
        finally:
            await pool.stop()

    event_loop.run_until_complete(run())


def test_timed_game_from_a_position_and_flag(client):
    fen = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
    game = client.post("/api/play/games", json={"bot_id": "sam", "player_color": "white", "time_control": "3+2", "fen": fen}).json()
    assert game["start_fen"].startswith("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2") and game["time_control"] == "3+2"
    assert game["turn"] == "w" and "f1c4" in game["legal_moves"]
    r = client.post(f"/api/play/games/{game['id']}/move", json={"move": "Bc4"}).json()
    assert r["bot_move"] is not None and '[SetUp "1"]' in r["game"]["pgn"] and 'TimeControl "180+2"' in r["game"]["pgn"]
    flagged = client.post(f"/api/play/games/{game['id']}/flag").json()
    assert flagged["status"] == "finished" and flagged["termination"] == "timeout" and flagged["result"] == "0-1"
    # a black-to-move start position makes the bot move first when the player is white
    black_to_move = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    g2 = client.post("/api/play/games", json={"bot_id": "pip", "player_color": "white", "fen": black_to_move}).json()
    assert len(g2["moves"]) == 1 and g2["moves"][0]["by"] == "bot"
    assert client.post("/api/play/games", json={"bot_id": "pip", "player_color": "white", "fen": "junk"}).status_code == 400
    untimed = client.post("/api/play/games", json={"bot_id": "pip", "player_color": "white"}).json()
    assert client.post(f"/api/play/games/{untimed['id']}/flag").status_code == 409
    assert client.post("/api/content/reload").json()["lessons"] >= 7


def test_bot_chat_and_adaptive_coach(client):
    from backend.bots.selector import _adaptive
    coach = get_bot("coach")
    assert _adaptive(coach, chess.Board())[0] == coach.selection.temperature_cp
    behind = chess.Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKB1R w Qkq - 0 1")  # white (bot) is a rook down
    assert _adaptive(coach, behind)[0] < coach.selection.temperature_cp
    ahead = chess.Board("rnbqkb1r/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")  # black is a rook down
    t, r = _adaptive(coach, ahead)
    assert t > coach.selection.temperature_cp and r > 0
    assert _adaptive(get_bot("pip"), behind)[0] == get_bot("pip").selection.temperature_cp
    assert all(get_bot("max").chat[k] for k in ("capture_yours", "check_given", "bot_losing"))
    # a chat line can appear on a capture; run a few captures and expect at least one line
    from backend.routers.play import _chat_line
    import random as _random
    row = {"bot_id": "max", "status": "active"}
    b = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2")
    lines = {_chat_line(row, b, chess.Move.from_uci("e4d5"), chess.Move.from_uci("d8d5"), _random.Random(i)) for i in range(30)}
    assert any(line for line in lines)
