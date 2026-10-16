from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    with TestClient(create_app()) as c:
        yield c


def test_explore_search_families_line(client):
    root = client.get("/api/openings/explore").json()
    assert root["opening"] is None
    sans = [c["san"] for c in root["continuations"]]
    assert "e4" in sans and "d4" in sans
    assert root["continuations"][0]["lines_below"] > 100
    after_e4 = client.get("/api/openings/explore", params={"fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"}).json()
    assert after_e4["opening"]["name"] == "King's Pawn Game"
    assert any(c["san"] == "c5" and "Sicilian" in c["name"] for c in after_e4["continuations"])
    s = client.get("/api/openings/search", params={"q": "najdorf"}).json()
    assert s["results"] and all("Najdorf" in r["name"] for r in s["results"])
    fam = client.get("/api/openings/families").json()["families"]
    assert fam[0]["lines"] > 100 and any(f["name"] == "Sicilian Defense" for f in fam)
    line = client.get("/api/openings/line", params={"pgn": "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6"}).json()
    assert len(line["steps"]) == 11 and "Najdorf" in line["opening"]["name"]
    assert client.get("/api/openings/explore", params={"fen": "junk"}).status_code == 400
