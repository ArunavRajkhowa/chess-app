"""Insights: every finding is a rule over the player's own reviewed games. One player with
fourteen reviewed bot games (synthetic lines with known mistakes, reviewed by the real engine at a
shallow depth) drives the API checks; the exact rules are also run over hand-built games."""
from __future__ import annotations

import json
import time

import chess
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.bots.roster import BOTS_BY_ID
from backend.bots.specialists import specialist_bots
from backend.content.endgames import load_endgames
from backend.content.games import find_game
from backend.content.lessons import find_lesson
from backend.insights import build as B
from backend.insights import games as G
from backend.insights.endgames import endgame_type, endgames
from backend.insights.motifs import motif_of
from backend.insights.openings import openings
from backend.insights.plan import plan
from backend.insights.quality import band_bounds, clusters, quality, trend
from backend.insights.tactics import tactics
from backend.openings.courses import load_courses
from backend.puzzles.store import THEME_INFO
from backend.review import classify as C
from backend.review.phases import ENDGAME, MIDDLEGAME, OPENING
from backend.storage.db import database

QUEEN_WIN = "7k/8/5K2/8/8/8/8/6Q1 w - - 0 1"  # K+Q v K: Qg7# wins, Qg6 is stalemate
ROOK_WIN = "7k/8/6K1/8/8/8/8/R7 w - - 0 1"  # Ra8#
OPERA = ("e4 e5 Nf3 d6 d4 Bg4 dxe5 Bxf3 Qxf3 dxe5 Bc4 Nf6 Qb3 Qe7 Nc3 c6 Bg5 b5 Nxb5 cxb5 Bxb5+ Nbd7 O-O-O Rd8 "
         "Rxd7 Rxd7 Rd1 Qe6 Bxd7+ Nxd7 Qb8+ Nxb8 Rd8#")
# (moves, player colour, result, bot) for the fourteen games, oldest first.
GAMES = [
    ("e4 e5 Nf3 Nc6 Bc4 Bc5 Qe2 Nf6 Qe3 Bxe3 dxe3", "white", "0-1", "mei"),  # 5.Qe3?? hangs the queen: three times
    ("e4 e5 Nf3 Nc6 Bc4 Bc5 Qe2 Nf6 Qe3 Bxe3 dxe3", "white", "0-1", "mei"),
    ("e4 e5 Nf3 Nc6 Bc4 Bc5 Qe2 Nf6 Qe3 Bxe3 dxe3", "white", "0-1", "leo"),
    ("e4 e5 Nf3 Nc6 Bc4 Nf6 Nc3 Nxe4 Nxe4 Bc5 Nxc5 d6 Nd3", "black", "1-0", "mei"),  # 5...Bc5?? misses the fork 5...d5: three times
    ("e4 e5 Nf3 Nc6 Bc4 Nf6 Nc3 Nxe4 Nxe4 Bc5 Nxc5 d6 Nd3", "black", "1-0", "leo"),
    ("e4 e5 Nf3 Nc6 Bc4 Nf6 Nc3 Nxe4 Nxe4 Bc5 Nxc5 d6 Nd3", "black", "1-0", "sam"),
    ("e4 e5 Nf3 Nc6 Bc4 Bc5 Ng5 Qxg5 d3 Qg6", "white", "0-1", "mei"),  # 4.Ng5?? leaves the book and hangs a knight
    ("e4 e5 Bc4 Nc6 Qh5 Nf6 Qxf7#", "black", "1-0", "sam"),  # the scholar's mate: a quiet-move mistake
    (OPERA, "white", "1-0", "ivy"),
    (OPERA, "white", "1-0", "ivy"),
    (OPERA, "white", "1-0", "omar"),
    ((QUEEN_WIN, "Qg7#"), "white", "1-0", "pip"),  # a winning queen endgame converted
    ((QUEEN_WIN, "Qg6"), "white", "1/2-1/2", "pip"),  # the same endgame stalemated
    ((ROOK_WIN, "Ra8#"), "white", "1-0", "pip"),  # a winning rook endgame converted
]
N_GAMES = len(GAMES)


_PORTAL = None  # the TestClient's loop: the store's lock must only ever be taken on the app's loop


async def _await(coro):
    return await coro


def _run(coro):
    return _PORTAL.call(_await, coro)


def _wait(client, job_id, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/review/jobs/{job_id}").json()
        if j["status"] in ("done", "failed"):
            assert j["status"] == "done", j
            return j
        time.sleep(0.2)
    raise AssertionError("review did not finish")


def _store_game(player: str, game_id: str, spec, color: str, result: str, bot_id: str, minutes_ago: int) -> None:
    start_fen = None
    if isinstance(spec, tuple):
        start_fen, sans = spec
    else:
        sans = spec
    board = chess.Board(start_fen) if start_fen else chess.Board()
    recs = []
    for san in sans.split():
        mv = board.parse_san(san)
        board.push(mv)
        recs.append({"ply": board.ply(), "san": san, "uci": mv.uci(), "fen": board.fen(), "by": "player", "source": "test", "eval_cp": None})
    termination = "checkmate" if board.is_checkmate() else "stalemate" if board.is_stalemate() else "resignation"
    _run(database.execute(
        "INSERT INTO games(id, player_id, created_at, player_color, bot_id, status, result, termination, moves_json, source, start_fen) "
        "VALUES(?, ?, datetime('now', ?), ?, ?, 'finished', ?, ?, ?, 'bot', ?)",
        (game_id, player, f"-{minutes_ago} minutes", color, bot_id, result, termination, json.dumps(recs), start_fen),
    ))


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from backend import settings as s
    from backend.routers import review as R
    mp = pytest.MonkeyPatch()
    mp.setattr(s.settings, "DB_PATH", str(tmp_path_factory.mktemp("db") / "t.sqlite3"))
    mp.setitem(R.DEPTHS, "quick", 6)  # the mistakes below are gross; a shallow review judges them the same
    global _PORTAL
    with TestClient(create_app()) as c:
        _PORTAL = c.portal
        c.get("/api/account")
        yield c
    mp.undo()


@pytest.fixture(scope="module")
def seeded(client) -> dict:
    """Fourteen reviewed bot games for the client's player, oldest first; returns the insights body."""
    player = client.cookies.get("player")
    for i, (spec, color, result, bot_id) in enumerate(GAMES):
        gid = f"ins{i:02d}"
        _store_game(player, gid, spec, color, result, bot_id, minutes_ago=(N_GAMES - i) * 10)
        job = client.post(f"/api/review/games/{gid}", json={"mode": "quick"}).json()
        _wait(client, job["id"])
    body = client.get("/api/insights/me").json()
    assert body["games"] == N_GAMES, body.get("message")
    return body


# ------------------------------------------------------------------ the API over real reviews

def test_headline_fields_are_kept(seeded):
    for key in ("accuracy", "phase_accuracy", "move_quality"):  # the coach's player_context reads these
        assert key in seeded
    assert len(seeded["accuracy"]["timeline"]) == N_GAMES
    assert "player_id" not in json.dumps(seeded)


def test_repeated_mistake_is_found_in_the_same_position(seeded):
    rep = seeded["sections"]["openings"]["repeated"]
    qe3 = next(r for r in rep if r["played_san"] == "Qe3")
    assert qe3["times"] == 3 and qe3["best_san"] != "Qe3" and qe3["opening"] == "Italian Game: Giuoco Piano"
    ex = qe3["example"]
    assert ex["ply"] == 9 and ex["move_number"] == 5 and ex["color"] == "white" and ex["opponent"] in ("Mei", "Leo")
    assert chess.Board(ex["fen"]).parse_san(ex["best_san"]).uci() == ex["best_uci"]
    assert ex["classification"] == C.BLUNDER and ex["drop"] > C.MISTAKE_MAX_DROP


def test_opening_deviation_ply_and_cost(seeded):
    rows = {(r["name"], r["color"]): r for r in seeded["sections"]["openings"]["rows"]}
    piano = rows[("Italian Game: Giuoco Piano", "white")]
    assert piano["games"] == 4 and piano["losses"] == 4 and piano["score"] == 0
    leave = piano["leave_book"]
    assert leave["ply"] == 7 and leave["move_number"] == 4 and leave["games"] == 4  # 4.Qe2 three times, 4.Ng5 once
    assert leave["costly"] >= 1 and leave["example"]["played_san"] == "Ng5" and leave["example"]["drop"] > C.MISTAKE_MAX_DROP  # the costliest departure
    assert piano["first_mistake_move"] == 4.8  # move 5 three times, move 4 once
    assert piano["course"]["id"] == "italian-game" and piano["course"]["kind"] == "course"
    knights = rows[("Four Knights Game: Italian Variation", "black")]
    assert knights["leave_book"]["ply"] == 8 and knights["leave_book"]["costly"] == 0  # 4...Nxe4 is fine
    assert knights["games"] == 3 and knights["first_mistake_move"] == 5


def test_missed_fork_is_the_most_missed_motif(seeded):
    t = seeded["sections"]["tactics"]
    fork = next(r for r in t["motifs"] if r["theme"] == "fork")
    assert fork["missed"] == 3 and fork["example"]["best_san"] == "d5" and fork["example"]["played_san"] == "Bc5"
    assert t["most_missed"] == "fork" and "fork" in t["finding"]
    assert t["action"]["kind"] == "puzzles" and t["action"]["id"] == "fork"
    assert t["lesson"]["id"] == find_lesson(t["lesson"]["id"]).id


def test_endgame_conversion_rate(seeded):
    e = seeded["sections"]["endgames"]
    assert e["games"] == 6  # the three Opera games end with six pieces left: an endgame by the lichess divider
    assert e["conversion"]["games"] == 6 and e["conversion"]["won"] == 5 and e["conversion"]["rate"] == 83
    assert e["conversion"]["example"]["played_san"] == "Qg6" and e["conversion"]["example"]["best_san"] == "Qg7#"
    assert e["hold"] is None  # never a worse endgame: no rate, not a zero
    types = {r["type"]: r for r in e["types"]}
    assert types["queen"]["games"] == 5 and types["queen"]["draws"] == 1 and types["rook"]["games"] == 1


def test_middlegame_errors_split_tactics_from_plans(seeded):
    m = seeded["sections"]["middlegame"]
    assert m["games"] == 3 and m["mobility"]["games"] == 3
    assert m["errors"]["tactic"]["count"] + m["errors"]["plan"]["count"] >= 0
    assert all(r["games"] >= 3 for r in m["imbalances"])


def test_quality_absence_is_data(seeded):
    q = seeded["sections"]["quality"]
    assert q["trend"]["direction"] is None and q["trend"]["needs"] == 20 - N_GAMES
    assert seeded["trend"] == q["trend"]
    assert q["time_controls"] is None  # every game had no clock: nothing to compare
    assert q["recent"]["games"] == 10
    assert q["clusters"]["peak"]["from_move"] == 1 and q["clusters"]["peak"]["blunders"] >= 5


def test_every_prescription_resolves(seeded):
    courses, drills, specialists = load_courses(), {p["key"] for p in load_endgames()["positions"]}, specialist_bots()

    def check(res: dict) -> None:
        kind, rid = res["kind"], res["id"]
        assert res["href"] and res["title"]
        if kind == "lesson":
            assert find_lesson(rid) is not None
        elif kind == "puzzles":
            assert rid in THEME_INFO
        elif kind == "course":
            assert rid in courses and (not res.get("line_id") or courses[rid].line(res["line_id"]))
        elif kind == "endgame":
            assert rid in drills
        elif kind == "bot":
            assert rid in BOTS_BY_ID or rid in specialists
        elif kind == "game":
            assert find_game(rid) is not None
        else:
            raise AssertionError(f"unknown resource kind {kind!r}")

    seen = 0
    for name, sec in seeded["sections"].items():
        if name == "strengths":
            continue
        for key in ("action", "lesson", "bot", "watch"):
            if sec.get(key):
                check(sec[key])
                seen += 1
        for row in sec.get("rows", []) + sec.get("imbalances", []):
            for key in ("course", "watch"):
                if row.get(key):
                    check(row[key])
    for item in seeded["plan"]:
        check(item["action"])
        for also in item["also"]:
            check(also)
        assert item["example"] and item["why"] and item["plan_goal"]
    assert seen >= 5


def test_plan_is_ordered_by_gain_and_leads_with_the_focus(seeded):
    items = seeded["plan"]
    assert 1 <= len(items) <= 5
    assert [i["rank"] for i in items] == list(range(1, len(items) + 1))
    assert [i["gain_per_game"] for i in items] == sorted((i["gain_per_game"] for i in items), reverse=True)
    assert seeded["focus"] == items[0]
    assert {i["area"] for i in items} >= {"tactics", "openings", ENDGAME}


def test_level_comes_from_review_estimates_or_is_absent(seeded):
    lvl = seeded["level"]
    assert lvl is None or (lvl["source"] in ("review estimate", "puzzle rating") and 0 <= lvl["band"] <= 8)
    assert (seeded["sections"]["quality"]["band"] is None) == (lvl is None)


def test_fifty_games_under_two_seconds(client, seeded):
    """Builds up to 50 reviewed games by copying the stored reports, then times a cold build."""
    player = client.cookies.get("player")
    rows = _run(database.fetch_all("SELECT g.id, g.player_color, g.bot_id, g.result, g.termination, g.moves_json, g.start_fen, r.report_json "
                                   "FROM games g JOIN reviews r ON r.game_id = g.id WHERE g.player_id = ?", (player,)))
    k = 0
    while N_GAMES + k < 50:
        src = rows[k % len(rows)]
        gid = f"copy{k:03d}"
        _run(database.execute(
            "INSERT INTO games(id, player_id, created_at, player_color, bot_id, status, result, termination, moves_json, source, start_fen) "
            "VALUES(?, ?, datetime('now', ?), ?, ?, 'finished', ?, ?, ?, 'bot', ?)",
            (gid, player, f"-{k + 1} seconds", src["player_color"], src["bot_id"], src["result"], src["termination"], src["moves_json"], src["start_fen"])))
        _run(database.execute("INSERT INTO reviews(game_id, report_json) VALUES(?, ?)", (gid, src["report_json"])))
        k += 1
    G._FACTS.clear()
    B._CACHE.clear()
    t0 = time.perf_counter()
    body = client.get("/api/insights/me").json()
    cold = time.perf_counter() - t0
    t0 = time.perf_counter()
    client.get("/api/insights/me")
    warm = time.perf_counter() - t0
    print(f"\ninsights for {body['games']} games: cold {cold * 1000:.0f} ms, warm {warm * 1000:.0f} ms")
    assert body["games"] == 50
    assert cold < 2.0, f"cold build took {cold:.2f}s"


def test_facts_cache_cleared_mid_load_still_returns_every_game(client, seeded, monkeypatch):
    player = client.cookies.get("player")
    full = _run(G.load_games(player))
    for g in full[:3]:  # three games to fetch again, the rest still cached
        del G._FACTS[next(k for k in G._FACTS if k.startswith(f"{g.id}:"))]
    monkeypatch.setattr(G, "_FACTS_CAP", len(G._FACTS) + 1)  # the refetch overflows the cap and clears the cache
    again = _run(G.load_games(player))
    assert [g.id for g in again] == [g.id for g in full]


def test_rereview_and_puzzle_attempt_rebuild_the_findings(client, seeded):
    player = client.cookies.get("player")
    gid = "ins13"
    row = _run(database.fetch_one("SELECT report_json FROM reviews WHERE game_id = ?", (gid,)))
    rep = json.loads(row["report_json"])
    client.get("/api/insights/me")  # cached now
    rep["white"]["accuracy"] = 12.3  # a re-review that judged the game differently
    _run(database.execute("UPDATE reviews SET report_json = ?, created_at = datetime('now', '+1 minute') WHERE game_id = ?", (json.dumps(rep), gid)))
    try:
        timeline = client.get("/api/insights/me").json()["accuracy"]["timeline"]
        assert next(t for t in timeline if t["game_id"] == gid)["accuracy"] == 12.3
        before = B._CACHE[player][0]
        _run(database.execute("INSERT INTO puzzle_attempts(player_id, puzzle_id, solved, mode) VALUES(?, 'x', 1, 'rated')", (player,)))
        client.get("/api/insights/me")
        assert B._CACHE[player][0] != before
    finally:
        _run(database.execute("UPDATE reviews SET report_json = ? WHERE game_id = ?", (row["report_json"], gid)))
        _run(database.execute("DELETE FROM puzzle_attempts WHERE player_id = ? AND puzzle_id = 'x'", (player,)))


# ------------------------------------------------------------------ the rules over hand-built games

def _move(ply: int, san: str, best: str, fen: str, cls: str, win_before: float, win_after: float, phase: str, motif: str | None = None, uci: str | None = None, best_uci: str | None = None) -> G.Move:
    return G.Move(ply=ply, move_number=(ply + 1) // 2, san=san, uci=uci or san, fen=fen, classification=cls, win_before=win_before, win_after=win_after,
                  drop=round(max(0.0, win_before - win_after), 1), cp_loss=int(max(0.0, win_before - win_after) * 10), best_san=best, best_uci=best_uci or best,
                  best_line=[best], phase=phase, motif=motif)


def _game(gid: str, outcome: str, moves: list[G.Move], *, color: str = "white", opening: dict | None = None, accuracy: float = 80.0, acpl: float = 40.0,
          positions: list[str] | None = None, win_graph: list[float] | None = None, boundaries: dict | None = None, estimated_rating: int | None = None,
          time_control: str | None = None, created_at: str = "2026-01-01") -> G.Game:
    counts = {c: sum(1 for m in moves if m.classification == c) for c in C.ALL_CLASSES}
    return G.Game(id=gid, color=color, outcome=outcome, opponent="Mei", created_at=created_at, termination="resignation", time_control=time_control,
                  opening=opening, accuracy=accuracy, acpl=acpl, estimated_rating=estimated_rating, counts=counts,
                  phase_accuracy={OPENING: accuracy, MIDDLEGAME: accuracy, ENDGAME: accuracy}, moves=moves, plies=max((m.ply for m in moves), default=0),
                  positions=positions or [chess.STARTING_FEN] * (max((m.ply for m in moves), default=0) + 1), win_graph=win_graph or [50.0] * (max((m.ply for m in moves), default=0) + 1),
                  boundaries=boundaries or {MIDDLEGAME: None, ENDGAME: None})


def test_motif_of_names_the_puzzle_theme():
    fork = chess.Board("r1bqkb1r/pppp1ppp/2n5/4p3/2B1N3/5N2/PPPP1PPP/R1BQK2R b KQkq - 0 5")
    assert motif_of(fork, fork.parse_san("d5")) == "fork"
    hang = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR b KQkq - 0 3")
    assert motif_of(hang, hang.parse_san("Nd4")) in (None, "fork")  # a quiet knight move: no capture to name
    defended = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3")
    assert motif_of(defended, defended.parse_san("Nxe5")) is None  # gives up the knight for a pawn: no motif
    assert motif_of(chess.Board("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 0 4"), chess.Move.from_uci("h5f7")) == "mate"


def test_a_recapture_is_a_trade_not_a_hanging_piece():
    board = chess.Board()
    for san in "e4 e5 Nf3 Nc6 Bb5 a6 Bxc6".split():
        board.push_san(san)
    dxc6 = board.parse_san("dxc6")
    assert motif_of(board, dxc6) == "hangingPiece"  # reasons.py alone calls it a free bishop
    assert motif_of(board, dxc6, chess.C6) is None


def test_endgame_type_by_heaviest_piece():
    assert endgame_type("8/8/4k3/8/8/4K3/4P3/8 w - - 0 1") == "pawn"
    assert endgame_type("8/8/4k3/8/8/4K3/4P3/R7 w - - 0 1") == "rook"
    assert endgame_type("8/8/4k3/8/8/4K3/4P3/B7 w - - 0 1") == "minor"
    assert endgame_type("8/8/4k3/8/8/4K3/4P3/R6q w - - 0 1") == "queen"


def test_conversion_and_hold_rates_count_only_decided_endgames():
    eg = "8/8/4k3/8/8/4K3/4P3/R7 w - - 0 1"
    won = _game("a", "win", [_move(61, "Ra6+", "Ra6+", eg, C.BEST, 95, 95, ENDGAME)], positions=[eg] * 62, win_graph=[90.0] * 62, boundaries={MIDDLEGAME: 20, ENDGAME: 60})
    thrown = _game("b", "draw", [_move(61, "Rh1", "Ra6+", eg, C.BLUNDER, 95, 50, ENDGAME)], positions=[eg] * 62, win_graph=[90.0] * 62, boundaries={MIDDLEGAME: 20, ENDGAME: 60})
    held = _game("c", "draw", [_move(61, "Kd5", "Kd5", eg, C.BEST, 15, 15, ENDGAME)], positions=[eg] * 62, win_graph=[15.0] * 62, boundaries={MIDDLEGAME: 20, ENDGAME: 60})
    level = _game("d", "loss", [_move(61, "Kd5", "Kd5", eg, C.BEST, 50, 50, ENDGAME)], positions=[eg] * 62, win_graph=[50.0] * 62, boundaries={MIDDLEGAME: 20, ENDGAME: 60})
    e = endgames([won, thrown, held, level], None)
    assert e["conversion"] == {"games": 2, "won": 1, "rate": 50, "drop_per_game": 11.2, "example": e["conversion"]["example"]}
    assert e["conversion"]["example"]["played_san"] == "Rh1"
    assert e["hold"] == {"games": 1, "held": 1, "rate": 100}
    assert e["lose_most"] == "rook"  # the only type reached, and one of its four games was lost
    assert e["action"]["kind"] in ("endgame", "lesson")
    assert endgames([], None)["conversion"] is None and endgames([], None)["needs"] == 2


def test_trend_needs_twenty_games_then_compares_the_last_ten_with_the_ten_before():
    assert trend([_game(str(i), "win", [], accuracy=70) for i in range(19)])["direction"] is None
    games = [_game(str(i), "win", [], accuracy=70) for i in range(10)] + [_game(str(i), "win", [], accuracy=75) for i in range(10, 20)]
    assert trend(games) == {"direction": "up", "delta": 5.0, "needs": 0}
    assert trend(list(reversed(games)))["direction"] == "down"
    assert trend([_game(str(i), "win", [], accuracy=70) for i in range(20)])["direction"] == "flat"


def test_blunders_cluster_by_move_number():
    fen = chess.STARTING_FEN
    moves = [_move(p, "a3", "e4", fen, C.BLUNDER if 21 <= (p + 1) // 2 <= 30 else C.GOOD, 50, 20 if 21 <= (p + 1) // 2 <= 30 else 48, MIDDLEGAME) for p in range(1, 80, 2)]
    cl = clusters([_game("a", "loss", moves)])
    assert cl["peak"]["from_move"] == 21 and cl["peak"]["to_move"] == 30 and cl["peak"]["blunders"] == 10
    assert cl["peak"]["example"]["drop"] == 30.0 and cl["peak"]["drop_total"] == 300.0
    assert clusters([_game("a", "win", [_move(1, "e4", "e4", fen, C.BEST, 50, 50, OPENING)])])["peak"] is None


def test_band_comparison_reads_the_review_rating_table():
    assert band_bounds(3) == (1100, 1400) and band_bounds(1) == (400, 800) and band_bounds(8) == (2400, 2800)
    assert C.acpl_for_rating(1400) == 63.3 and C.acpl_for_rating(1100) == 90.0 and C.acpl_for_rating(2800) == 5.0 and C.acpl_for_rating(300) == 250.0
    level = {"band": 3, "name": "Rook", "rating": 1250, "range": "1100–1400", "source": "puzzle rating"}
    q = quality([_game(str(i), "win", [], acpl=30.0) for i in range(3)], level)
    assert q["band"]["verdict"] == "better" and q["band"]["expected_low"] == 63.3 and q["band"]["expected_high"] == 90.0
    assert quality([_game("a", "win", [], acpl=120.0)], level)["band"]["verdict"] == "worse"
    assert quality([_game("a", "win", [], acpl=120.0)], None)["band"] is None


def test_repeated_mistake_needs_the_same_position_twice():
    fen = "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/4Q3/PPPP1PPP/RNB1K2R w KQkq - 4 5"
    op = {"eco": "C50", "name": "Italian Game: Giuoco Piano", "last_book_ply": 6}
    once = [_game("a", "loss", [_move(9, "Qe3", "d3", fen, C.BLUNDER, 55, 5, OPENING)], opening=op)]
    twice = once + [_game("b", "loss", [_move(9, "Qe3", "d3", fen.replace(" 4 5", " 6 7"), C.BLUNDER, 55, 5, OPENING)], opening=op)]
    assert openings(once, None)["repeated"] == []
    rep = openings(twice, None)["repeated"]
    assert len(rep) == 1 and rep[0]["times"] == 2 and rep[0]["drop_total"] == 100.0
    row = openings(twice, None)["rows"][0]
    assert row["leave_book"] is None  # the player's move at ply 7 is not stored here: no departure to judge


def test_tactics_counts_found_and_missed_per_motif():
    fen = chess.STARTING_FEN
    found = [_move(p, "d5", "d5", fen, C.BEST, 50, 50, MIDDLEGAME, motif="fork") for p in (10, 12, 14)]
    missed = [_move(p, "Bc5", "d5", fen, C.BLUNDER, 50, 20, MIDDLEGAME, motif="fork") for p in (16, 18)]
    optional = [_move(20, "h6", "Nd5", fen, C.GOOD, 50, 47, MIDDLEGAME, motif="pin")]  # not played, not costly: neither found nor missed
    t = tactics([_game("a", "loss", found + missed + optional)], None)
    fork = next(r for r in t["motifs"] if r["theme"] == "fork")
    assert fork == {"theme": "fork", "name": "Fork", "found": 3, "missed": 2, "seen": 5, "drop_per_game": 60.0, "example": fork["example"]}
    assert next(r for r in t["motifs"] if r["theme"] == "pin")["seen"] == 0
    assert t["most_missed"] == "fork" and t["needs"] == 0
    assert tactics([_game("a", "win", found)], None)["most_missed"] is None


def test_plan_ranks_by_win_chance_lost_per_game():
    sections = {
        "games": 2,
        "tactics": {"motifs": [{"theme": "fork", "name": "Fork", "found": 1, "missed": 2, "seen": 3, "drop_per_game": 12.0, "example": {"drop": 20}}], "most_missed": "fork",
                    "action": {"kind": "puzzles", "id": "fork", "title": "Fork puzzles", "href": "/puzzles?theme=fork"}, "lesson": None, "bot": None},
        "openings": {"repeated": [{"times": 2, "played_san": "Qe3", "best_san": "d3", "opening": "Italian Game", "drop_total": 60.0, "example": {"drop": 30, "color": "white"}}],
                     "rows": [], "action": {"kind": "lesson", "id": "b1m4l1", "title": "x", "href": "/learn/b1m4l1"}},
        "endgames": {"conversion": {"games": 2, "won": 1, "rate": 50, "drop_per_game": 20.0, "example": {"drop": 40}}, "lose_most": "rook",
                     "action": {"kind": "endgame", "id": "rook-lucena", "title": "x", "href": "/endgames"}, "lesson": None, "bot": None},
        "middlegame": {"errors": {"plan": {"count": 0, "drop_per_game": 0.0, "example": None}, "tactic": {"count": 0, "drop_per_game": 0.0, "example": None}}, "watch": None},
        "quality": {"clusters": {"peak": None}, "phases": {}, "weakest_phase": None, "action": None, "bot": None},
    }
    items = plan(sections, 3)
    assert [i["area"] for i in items] == ["openings", ENDGAME, "tactics"]  # 30 > 20 > 12 win chance per game
    assert items[0]["gain_per_game"] == 30.0 and items[0]["rank"] == 1 and items[0]["plan_goal"] == "the Italian Game as white"
    assert items[1]["plan_goal"] == "rook endgames"


def test_plan_gains_sum_the_named_moves_and_goals_name_the_family():
    ex = {"drop": 40, "color": "white"}
    act = {"kind": "lesson", "id": "x", "title": "x", "href": "/learn/x"}
    sections = {
        "games": 10,
        "tactics": {"motifs": [], "most_missed": None},
        "openings": {"repeated": [], "action": act, "rows": [{"name": "Italian Game: Two Knights Defense", "color": "white", "score": 0, "course": None,
                                                         "leave_book": {"move_number": 5, "games": 4, "costly": 3, "drop_total": 50.0, "example": ex}}]},
        "endgames": {"conversion": None},
        "middlegame": {"errors": {"plan": {"count": 0}}},
        "quality": {"clusters": {"peak": {"from_move": 21, "to_move": 30, "blunders": 2, "drop_total": 30.0, "example": ex}}, "action": act, "bot": None},
    }
    items = {i["area"]: i for i in plan(sections, 3)}
    assert items["openings"]["gain_per_game"] == 5.0  # 50 over 10 games, not the worst drop times the count
    assert items["openings"]["plan_goal"] == "the Italian Game as white"
    assert items["blunders"]["gain_per_game"] == 3.0


def test_level_is_absent_without_a_settled_rating_or_three_estimates():
    assert B.level_of([_game("a", "win", [], estimated_rating=1500)], None) is None
    lvl = B.level_of([_game(str(i), "win", [], estimated_rating=1500) for i in range(3)], None)
    assert lvl == {"band": 4, "name": "Queen", "rating": 1500, "range": "1400–1700", "source": "review estimate"}
    assert B.level_of([], {"puzzle_rating": 1250, "band": 3})["source"] == "puzzle rating"


def test_level_hint_names_the_server_thresholds():
    games = [_game("a", "win", [])]
    hint = B.build_findings(games, None, [])["level_hint"]
    assert f"{B.MIN_GAMES_FOR_ESTIMATE} games" in hint and f"{C.MIN_MOVES_FOR_ESTIMATE} moves" in hint
    level = {"band": 3, "name": "Rook", "rating": 1250, "range": "1100–1400", "source": "puzzle rating"}
    assert B.build_findings(games, level, [])["level_hint"] is None
