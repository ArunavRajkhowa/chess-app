"""Puzzle ratings come from the puzzle's shape; the rating never jumps a whole level on one result."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.puzzles.difficulty import MAX_RATING, MIN_RATING, difficulty
from backend.puzzles.glicko import MAX_STEP, Rating, update

HANGING = "6k1/5p1p/2r3b1/4N3/8/8/5PPP/6K1 w - - 0 1"  # Nxc6 wins a rook for free


def test_a_free_capture_is_easy_and_a_quiet_deflection_is_hard():
    easy = difficulty(HANGING, ["e5c6"], ["hangingPiece", "crushing", "short"], solver_first=True)
    quiet = difficulty("r5k1/p5pp/1p3p2/8/1b6/8/PP3PPP/3Q2K1 w - - 0 1", ["d1d5", "g8f8", "d5a8"], ["deflection", "quietMove", "advantage", "long"], solver_first=True)
    assert MIN_RATING <= easy < 800 < quiet <= MAX_RATING
    assert difficulty("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1", ["a1a8"], ["mateIn1", "mate", "backRankMate"], solver_first=True) <= 700


def test_the_library_is_spread_and_not_top_heavy():
    from backend.puzzles.store import load_library
    ratings = sorted(p.rating for p in load_library().all)
    assert ratings[0] >= MIN_RATING and ratings[-1] <= MAX_RATING
    assert 700 <= ratings[len(ratings) // 2] <= 1200
    assert sum(1 for r in ratings if r >= 1600) <= len(ratings) // 10


def test_one_puzzle_moves_the_rating_by_at_most_a_step():
    r = Rating()
    for _ in range(3):
        nxt = update(r, Rating(rating=2000, rd=60), 1.0)
        assert 0 < nxt.rating - r.rating <= MAX_STEP
        r = nxt
    down = update(r, Rating(rating=600, rd=60), 0.0)
    assert -MAX_STEP <= down.rating - r.rating < 0


def test_a_short_game_gets_no_rating_estimate(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    with TestClient(create_app()) as client:
        r = client.post("/api/review/import", json={"pgn": "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0", "mode": "quick"}).json()
        import time
        for _ in range(200):
            if client.get(f"/api/review/jobs/{r['job']['id']}").json()["status"] == "done":
                break
            time.sleep(0.1)
        report = client.get(f"/api/review/games/{r['game_id']}").json()["report"]
        assert report["white"]["estimated_rating"] is None and report["black"]["estimated_rating"] is None
        assert client.get("/api/narration", params={"text": "Knight to f3."}).status_code == 204  # voices off in tests
        assert client.get("/api/narration/voice").json()["tts"] is False
