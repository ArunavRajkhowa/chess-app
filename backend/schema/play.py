"""Typed shapes for the play API: what the browser sends and what a game looks like on the wire."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PlayerColor = Literal["white", "black"]
GameStatus = Literal["active", "finished"]


class NewGameRequest(BaseModel):
    bot_id: str
    player_color: Literal["white", "black", "random"] = "white"
    coach_mode: bool = False


class MoveRequest(BaseModel):
    move: str = Field(description="UCI (e2e4, e7e8q) or SAN (Nf3, O-O)")
    want_eval: bool = False


class MoveRecord(BaseModel):
    ply: int
    san: str
    uci: str
    fen: str
    by: Literal["player", "bot"]
    source: str | None = None
    eval_cp: int | None = None


class GameState(BaseModel):
    id: str
    fen: str
    pgn: str
    moves: list[MoveRecord]
    status: GameStatus
    result: str | None
    termination: str | None
    player_color: PlayerColor
    bot: dict
    coach_mode: bool
    opening: dict | None
    last_move: list[str] | None
    in_check: bool
    turn: Literal["w", "b"]
    legal_moves: list[str]
    threats: list[dict] = []


class MoveResponse(BaseModel):
    game: GameState
    player_move: MoveRecord
    bot_move: MoveRecord | None
    bot_says: str | None = None
    eval_cp: int | None = None
    eval_text: str | None = None


class HintResponse(BaseModel):
    move_uci: str
    move_san: str
    eval_text: str
    line_san: list[str]
    threats: list[str]
