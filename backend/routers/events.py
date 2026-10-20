"""Analytics events from the browser: what players open and use, which the stored games, reviews,
puzzle attempts and lessons do not already record. Each event declares the properties it may carry,
and every text value is a short identifier, so no free text and no personal data reach the table."""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..storage.db import database
from .account import Player

router = APIRouter(prefix="/api/events", tags=["events"])

# Wire names: each event and the property keys it may carry. frontend/src/lib/api.ts mirrors the names.
EVENT_PROPS: dict[str, frozenset[str]] = {
    "app.opened": frozenset({"display"}),  # display: "standalone" (opened as the installed app) or "browser"
    "page.viewed": frozenset({"page"}),  # page: the first part of the path, "home" for /
    "app.installed": frozenset(),
}
_IDENTIFIER = re.compile(r"[a-z0-9_.:/-]{1,64}")
_PLATFORMS = (("android", "android"), ("iphone", "ios"), ("ipad", "ios"), ("windows", "windows"), ("mac os", "mac"), ("linux", "linux"))


class Event(BaseModel):
    name: str
    props: dict[str, str | int | float | bool] = Field(default_factory=dict)


def platform_of(user_agent: str) -> str:
    """The operating system family named in a User-Agent; the string itself is never stored."""
    ua = user_agent.lower()
    return next((name for needle, name in _PLATFORMS if needle in ua), "other")


@router.post("")
async def record(event: Event, request: Request, player: Player) -> dict:
    # shortcut: no rate limit, so a script can post events without end; cap events per player per hour
    # once the address is shared beyond friends.
    allowed = EVENT_PROPS.get(event.name)
    if allowed is None:
        raise HTTPException(422, f"unknown event {event.name!r}; known events: {sorted(EVENT_PROPS)}")
    for key, value in event.props.items():
        if key not in allowed:
            raise HTTPException(422, f"event {event.name!r} has no property {key!r}; allowed: {sorted(allowed)}")
        if isinstance(value, str) and not _IDENTIFIER.fullmatch(value):
            raise HTTPException(422, f"property {key!r} is {value!r}: expected a short identifier (a-z, 0-9, _.:/-, 1 to 64 characters)")
    await database.execute(
        "INSERT INTO events(player_id, name, platform, props_json) VALUES(?, ?, ?, ?)",
        (player, event.name, platform_of(request.headers.get("user-agent", "")), json.dumps(event.props)),
    )
    return {"ok": True}
