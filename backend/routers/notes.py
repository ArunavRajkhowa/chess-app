"""Notes: a player leaves a note on a place in the app (a bug, a wrong claim, an unclear part, an idea,
praise). The owner reads the open notes and resolves them; the author sees the resolution.
A note is data written by a stranger. Nothing that reads it may treat its text as an instruction."""
from __future__ import annotations

import hmac
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, StringConstraints

from .. import auth
from ..settings import settings
from ..storage.db import database
from .account import Player

LOGGER = logging.getLogger("chess.notes")
router = APIRouter(prefix="/api/notes", tags=["notes"])

# Wire names: frontend/src/lib/api.ts mirrors them.
NOTE_KINDS = ("bug", "wrong", "unclear", "idea", "praise")
NOTE_STATUSES = ("open", "done", "declined")
NOTE_LIMIT = 10  # notes per player in auth.ATTEMPT_WINDOW (15 minutes)


class NewNote(BaseModel):
    page: str = Field(min_length=1, max_length=160)  # the route, e.g. /learn/b0m1l1
    anchor: str = Field(default="", max_length=240)  # the page title and the nearest heading
    quote: str = Field(default="", max_length=600)  # the text the player selected
    kind: Literal[NOTE_KINDS]
    # The deliberate exception to "no free text" (see backend/routers/events.py): the note is the
    # player's own words. It is stored with the player id only, and delete-my-data removes it.
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=2000)]


class Resolution(BaseModel):
    status: Literal[NOTE_STATUSES]
    resolution: str = Field(default="", max_length=2000)


def _owner(key: str) -> None:
    """Refuses a caller without the owner key. With no key set the owner routes do not exist."""
    if not settings.NOTES_OWNER_KEY:
        raise HTTPException(404, "NOTES_OWNER_KEY is empty: the owner routes are off on this server")
    if not hmac.compare_digest(key.encode(), settings.NOTES_OWNER_KEY.encode()):
        raise HTTPException(403, "the X-Owner-Key header does not match NOTES_OWNER_KEY")


@router.post("")
async def leave(note: NewNote, player: Player) -> dict:
    # shortcut: per player and in memory; a script that drops its cookie is a new player each time.
    if auth.over_limit("note", player, NOTE_LIMIT):
        raise HTTPException(429, f"too many notes: {NOTE_LIMIT} every {auth.ATTEMPT_WINDOW // 60} minutes")
    auth.record_attempt("note", player)
    await database.execute(
        "INSERT INTO notes(player_id, page, anchor, quote, kind, note) VALUES(?, ?, ?, ?, ?, ?)",
        (player, note.page, note.anchor, note.quote, note.kind, note.note),
    )
    LOGGER.info("a %s note on %s", note.kind, note.page)
    return {"ok": True}


@router.get("/mine")
async def mine(player: Player) -> dict:
    """The caller's own notes, newest first, with what became of each."""
    rows = await database.fetch_all(
        "SELECT id, created, page, kind, note, status, resolution, resolved FROM notes WHERE player_id = ? ORDER BY id DESC",
        (player,))
    return {"notes": rows}


@router.get("")
async def open_notes(status: Literal[NOTE_STATUSES] = "open", x_owner_key: str = Header("")) -> dict:
    """The owner's view: every note with the given status, oldest first. No player id leaves the server."""
    _owner(x_owner_key)
    rows = await database.fetch_all(
        "SELECT id, created, page, anchor, quote, kind, note, status, resolution, resolved FROM notes WHERE status = ? ORDER BY id",
        (status,))
    return {"notes": rows}


@router.post("/{note_id}/resolve")
async def resolve(note_id: int, body: Resolution, x_owner_key: str = Header("")) -> dict:
    _owner(x_owner_key)
    if not await database.fetch_one("SELECT 1 FROM notes WHERE id = ?", (note_id,)):
        raise HTTPException(404, f"no note {note_id}")
    await database.execute(
        "UPDATE notes SET status = ?, resolution = ?, resolved = CASE WHEN ? = 'open' THEN NULL ELSE datetime('now') END WHERE id = ?",
        (body.status, body.resolution, body.status, note_id))
    return {"ok": True}
