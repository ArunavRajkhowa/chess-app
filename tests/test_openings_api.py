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
    after_e4 = client.get("/api/openings/explore", params={"moves": "e2e4"}).json()
    assert after_e4["opening"]["name"] == "King's Pawn Game"
    assert any(c["san"] == "c5" and "Sicilian" in c["name"] for c in after_e4["continuations"])
    s = client.get("/api/openings/search", params={"q": "najdorf"}).json()
    assert s["results"] and all("Najdorf" in r["name"] for r in s["results"])
    fam = client.get("/api/openings/families").json()["families"]
    assert fam[0]["lines"] > 100 and any(f["name"] == "Sicilian Defense" for f in fam)
    line = client.get("/api/openings/line", params={"pgn": "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6"}).json()
    assert len(line["steps"]) == 11 and "Najdorf" in line["opening"]["name"]
    assert client.get("/api/openings/explore", params={"moves": "e2e4 e2e4"}).status_code == 400


def test_explore_walks_the_open_sicilian(client):
    def explore(moves: str) -> dict:
        return client.get("/api/openings/explore", params={"moves": moves}).json()

    after_cxd4 = explore("e2e4 c7c5 g1f3 d7d6 d2d4 c5d4")
    conts = {c["san"]: c for c in after_cxd4["continuations"]}
    assert after_cxd4["continuations"][0]["san"] == "Nxd4"  # most named lines pass through it
    assert conts["Nxd4"]["name"] is None and conts["Nxd4"]["eco"] is None
    after_nxd4 = explore("e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4")
    assert after_nxd4["opening"]["name"] == "Sicilian Defense"  # deepest named position in the moves
    assert after_nxd4["opening"]["pgn"] == "1. e4 c5 2. Nf3 d6 3. d4 cxd4"
    below = {c["san"]: c["lines_below"] for c in after_nxd4["continuations"]}
    assert below["Nf6"] > 1 and below["g6"] > 0
