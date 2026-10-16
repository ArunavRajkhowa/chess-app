"""Game rows: the stored form of a bot game. The move list is the record; the PGN is derived."""
from __future__ import annotations

import json
import uuid
from typing import Any

from .db import database


async def insert_game(*, player_color: str, bot_id: str, coach_mode: bool, time_control: str | None = None,
                      start_fen: str | None = None) -> str:
    game_id = uuid.uuid4().hex[:12]
    await database.execute(
        "INSERT INTO games(id, player_color, bot_id, time_control, status, moves_json, coach_mode, start_fen) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (game_id, player_color, bot_id, time_control, "active", "[]", int(coach_mode), start_fen),
    )
    return game_id


async def read_game(game_id: str) -> dict[str, Any] | None:
    row = await database.fetch_one("SELECT * FROM games WHERE id = ?", (game_id,))
    if row:
        row["moves"] = json.loads(row.pop("moves_json"))
    return row


async def save_game(game_id: str, *, moves: list[dict], pgn: str, status: str, result: str | None,
                    termination: str | None, opening_eco: str | None, opening_name: str | None) -> None:
    await database.execute(
        "UPDATE games SET moves_json=?, pgn=?, status=?, result=?, termination=?, opening_eco=?, "
        "opening_name=?, updated_at=datetime('now') WHERE id=?",
        (json.dumps(moves), pgn, status, result, termination, opening_eco, opening_name, game_id),
    )


async def list_games(limit: int = 50) -> list[dict[str, Any]]:
    return await database.fetch_all(
        "SELECT id, created_at, updated_at, player_color, bot_id, time_control, status, result, termination, "
        "opening_eco, opening_name, white_name, black_name, source, coach_mode, start_fen, json_array_length(moves_json) AS plies "
        "FROM games ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    )
