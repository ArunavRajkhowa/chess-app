"""Specialist bots: generated for every course, middlegame theme and endgame theme at four ratings;
an opening specialist stays in its family, an endgame specialist starts from a verified position,
and a guided note names only moves that are legal where it names them."""
from __future__ import annotations

import re

import chess
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.bots.roster import BOTS, SPECIALTY_ENDGAME, SPECIALTY_MIDDLEGAME, SPECIALTY_OPENING, TIER_SPECIALIST
from backend.bots.specialists import RATINGS, specialist_bots
from backend.content.endgames import load_endgames
from backend.openings.book import _position_key, load_book
from backend.openings.courses import load_courses

_SAN = re.compile(r"\b(?:O-O(?:-O)?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?)\b")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    with TestClient(create_app()) as c:
        yield c


def test_specialists_cover_every_course_and_endgame_theme_at_every_rating():
    bots = specialist_bots()
    assert not set(bots) & {b.id for b in BOTS}
    for course in load_courses().values():
        for elo in RATINGS:
            assert f"{SPECIALTY_OPENING}-{course.id}-{elo}" in bots
            assert f"{SPECIALTY_MIDDLEGAME}-{course.id}-{elo}" in bots
    for theme in load_endgames()["themes"]:
        for elo in RATINGS:
            b = bots[f"{SPECIALTY_ENDGAME}-{theme['key']}-{elo}"]
            assert b.specialty.start_fens and b.tier == TIER_SPECIALIST and b.elo == elo
    for key in ("attack", "positional"):
        assert bots[f"{SPECIALTY_MIDDLEGAME}-{key}-1400"].specialty.start_fens
    for b in bots.values():  # strength is depth and temperature, never the engine's Skill Level
        assert b.search.depth >= 1 and b.selection.temperature_cp >= 0


def test_bots_api_lists_specialists_with_their_specialty(client):
    bots = client.get("/api/bots").json()["bots"]
    classic = [b for b in bots if b["tier"] != TIER_SPECIALIST]
    assert len(classic) == len(BOTS) and all(b["specialty"] is None for b in classic)
    spec = [b for b in bots if b["tier"] == TIER_SPECIALIST]
    assert len(spec) == len(specialist_bots())
    assert {b["specialty"]["kind"] for b in spec} == {SPECIALTY_OPENING, SPECIALTY_MIDDLEGAME, SPECIALTY_ENDGAME}


def test_opening_specialist_plays_its_family_on_both_sides(client):
    book = load_book()
    # as Black against it: its first move must start a Sicilian line it can reach
    g = client.post("/api/play/games", json={"bot_id": "opening-sicilian-dragon-1400", "player_color": "black"}).json()
    assert g["moves"][0]["san"] == "e4"
    r = client.post(f"/api/play/games/{g['id']}/move", json={"move": "c7c5"}).json()
    board = chess.Board()
    for m in r["game"]["moves"]:
        board.push_uci(m["uci"])
    assert book.lookup(board) is not None and book.lookup(board).family == "Sicilian Defense"
    # as White: after 1.e4 it answers with the Sicilian
    g = client.post("/api/play/games", json={"bot_id": "opening-sicilian-dragon-1400", "player_color": "white"}).json()
    r = client.post(f"/api/play/games/{g['id']}/move", json={"move": "e2e4"}).json()
    assert r["bot_move"]["san"] == "c5" and r["bot_move"]["source"] == "book"


def test_endgame_specialist_starts_from_a_verified_position_on_the_task_side(client):
    rook = {p["key"]: p for p in load_endgames()["positions"] if p["theme"] == "rook"}
    keys = {_position_key(chess.Board(p["fen"])): p for p in rook.values()}
    mirrored = {_position_key(chess.Board(p["fen"]).mirror()): p for p in rook.values()}
    for color in ("white", "black"):
        g = client.post("/api/play/games", json={"bot_id": "endgame-rook-1800", "player_color": color}).json()
        start = chess.Board(g["start_fen"])
        record = keys.get(_position_key(start)) or mirrored.get(_position_key(start))
        assert record is not None, g["start_fen"]
        assert (start.turn == chess.WHITE) == (color == "white")  # the player has the task
        assert g["turn"] == color[0] and g["bot"]["specialty"]["key"] == "rook"


def test_middlegame_specialist_starts_from_a_level_master_game_position(client):
    g = client.post("/api/play/games", json={"bot_id": "middlegame-attack-1400", "player_color": "white"}).json()
    bot = specialist_bots()["middlegame-attack-1400"]
    assert g["start_fen"] in bot.specialty.start_fens
    from backend.routers.play import _START_VERDICTS, START_MAX_EDGE_CP
    assert abs(_START_VERDICTS[g["start_fen"]]) <= START_MAX_EDGE_CP


def test_opening_notes_name_only_moves_legal_after_the_book_move():
    from backend.bots.guide import opening_note
    from backend.study.reasons import opponent_to_move

    for course in load_courses().values():
        for line in course.lines + course.traps:
            before = chess.Board()
            for p in line.plies:
                move = chess.Move.from_uci(p["uci"])
                after = before.copy()
                after.push(move)
                note = opening_note(before, move) or ""
                legal = {b.san(m).rstrip("+#") for b in (before, after, opponent_to_move(after)) for m in b.legal_moves}
                bad = {t.rstrip("+#") for t in _SAN.findall(note) if len(t) >= 3} - legal
                assert not bad, f"{course.id}/{line.id} ply {p['ply']}: {note!r} names {bad}"
                before = after



def test_left_the_book_notes_name_only_moves_legal_where_they_are_named():
    from backend.bots.guide import opening_note
    from backend.study.reasons import opponent_to_move

    book = load_book()
    seen = set()
    for course in load_courses().values():
        for line in course.lines + course.traps:
            before = chess.Board()
            for p in line.plies:
                key = _position_key(before)
                if key in book.lines_through and key not in seen:
                    seen.add(key)
                    off = next((m for m in before.legal_moves if _position_key((b := before.copy(), b.push(m))[0]) not in book.lines_through), None)
                    note = opening_note(before, off) if off else None
                    if note:
                        main_mv = max(book.book_moves(before), key=lambda t: t[2])[0]
                        after_main = before.copy()
                        after_main.push(main_mv)
                        legal = {b.san(m).rstrip("+#") for b in (before, after_main, opponent_to_move(after_main)) for m in b.legal_moves}
                        bad = {t.rstrip("+#") for t in _SAN.findall(note) if len(t) >= 3} - legal
                        assert not bad, f"{course.id}/{line.id} ply {p['ply']}: {note!r} names {bad}"
                before.push(chess.Move.from_uci(p["uci"]))

def test_guided_notes_name_only_legal_moves(client):
    def legal_sans(boards):
        out = set()
        for b in boards:
            out |= {b.san(m).rstrip("+#") for m in b.legal_moves}
        return out

    # opening specialist: a book move, then leaving the book
    g = client.post("/api/play/games", json={"bot_id": "opening-sicilian-dragon-1000", "player_color": "white"}).json()
    before = chess.Board()
    r = client.post(f"/api/play/games/{g['id']}/move", json={"move": "e2e4", "want_guide": True}).json()
    assert "book move" in r["guide"]
    after_player = before.copy()
    after_player.push_uci("e2e4")
    after_bot = chess.Board(r["game"]["fen"])
    assert {t.rstrip("+#") for t in _SAN.findall(r["guide"]) if len(t) >= 3} <= legal_sans([before, after_player, after_bot])
    book = load_book()  # a move the book has no line for, so the note is "you left the book"
    off_book = next(m for m in after_bot.legal_moves if _position_key((b := after_bot.copy(), b.push(m))[0]) not in book.lines_through)
    r2 = client.post(f"/api/play/games/{g['id']}/move", json={"move": off_book.uci(), "want_guide": True}).json()
    assert "left the book" in r2["guide"] and "main line" in r2["guide"]
    assert {t.rstrip("+#") for t in _SAN.findall(r2["guide"]) if len(t) >= 3} <= legal_sans([after_bot, chess.Board(r2["game"]["moves"][-2]["fen"]), chess.Board(r2["game"]["fen"])])

    # endgame specialist: the verdict and the record's rule
    g = client.post("/api/play/games", json={"bot_id": "endgame-checkmates-1000", "player_color": "white"}).json()
    start = chess.Board(g["start_fen"])
    move = next(iter(start.legal_moves))
    r = client.post(f"/api/play/games/{g['id']}/move", json={"move": move.uci(), "want_guide": True}).json()
    assert "Goal: checkmate" in r["guide"] and "The rule:" in r["guide"]
    after_player = start.copy()
    after_player.push(move)
    assert {t.rstrip("+#") for t in _SAN.findall(r["guide"]) if len(t) >= 3} <= legal_sans([start, after_player])
    # without the opt-in there is no note
    assert client.post(f"/api/play/games/{g['id']}/move", json={"move": chess.Board(r["game"]["fen"]).san(next(iter(chess.Board(r["game"]["fen"]).legal_moves)))}).json()["guide"] is None
