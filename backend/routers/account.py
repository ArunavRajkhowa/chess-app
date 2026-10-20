"""Accounts: every visitor is a player from the first request, known by an httpOnly cookie that holds
a random id. Signing in with Google attaches a verified email to that player, so progress follows
the person to another device. The id is the cookie's secret: no response body ever carries it."""
from __future__ import annotations

import logging
import re
import secrets
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ..settings import settings
from ..storage.db import database

LOGGER = logging.getLogger("chess.account")
router = APIRouter(prefix="/api/account", tags=["account"])

PLAYER_COOKIE = "player"
COOKIE_DAYS = 400  # the longest lifetime Chrome keeps a cookie
_PLAYER_ID = re.compile(r"[0-9a-f]{32}")
GOOGLE_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")

# Every table with a player_id column. A guest who signs in to an existing account brings these rows along.
PLAYER_TABLES = ("games", "puzzle_attempts", "events")
# Per-player tables with one row per key: when the guest and the account both have a key, the account's row wins.
PLAYER_KEYED_TABLES = ("player_lessons", "player_values", "player_reviews")


def _set_player_cookie(request: Request, response: Response, player_id: str) -> None:
    response.set_cookie(PLAYER_COOKIE, player_id, max_age=COOKIE_DAYS * 86400, httponly=True, samesite="lax",
                        secure=request.url.scheme == "https")


async def current_player(request: Request, response: Response) -> str:
    """The caller's player id from the cookie; a request without one makes a new guest."""
    player_id = request.cookies.get(PLAYER_COOKIE, "")
    if _PLAYER_ID.fullmatch(player_id):
        return player_id
    player_id = secrets.token_hex(16)
    await database.execute("INSERT INTO players(id) VALUES(?)", (player_id,))
    _set_player_cookie(request, response, player_id)
    return player_id


Player = Annotated[str, Depends(current_player)]


class GoogleSignIn(BaseModel):
    credential: str  # the ID token that Google's button hands the page


@router.get("")
async def account(player: Player) -> dict:
    """Who is playing. The browser calls it first, so a new visitor has a cookie before anything else."""
    await database.execute("INSERT OR IGNORE INTO players(id) VALUES(?)", (player,))  # a cookie older than this database
    row = await database.fetch_one("SELECT email FROM players WHERE id = ?", (player,))
    return {"email": row["email"], "google_client_id": settings.GOOGLE_CLIENT_ID or None}


async def verify_google(credential: str) -> dict:
    """The token's claims, once Google confirms its signature and expiry and the audience is this app."""
    # shortcut: Google's tokeninfo endpoint checks the signature, one HTTP call per sign-in; verify against
    # Google's published keys instead if sign-ins reach thousands a day.
    async with httpx.AsyncClient(timeout=10) as http:
        r = await http.get(GOOGLE_TOKENINFO, params={"id_token": credential})
    if r.status_code != 200:
        raise HTTPException(401, f"Google did not accept the sign-in token (HTTP {r.status_code})")
    claims = r.json()
    if claims.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise HTTPException(401, f"the token is for client {claims.get('aud')!r}, not this server's GOOGLE_CLIENT_ID")
    if claims.get("iss") not in GOOGLE_ISSUERS or claims.get("email_verified") != "true":
        raise HTTPException(401, f"token issuer {claims.get('iss')!r} with email_verified {claims.get('email_verified')!r}: expected Google and 'true'")
    return claims


def _merge_statements(guest: str, owner: str) -> list[tuple[str, tuple]]:
    statements = [(f"UPDATE {t} SET player_id = ? WHERE player_id = ?", (owner, guest)) for t in PLAYER_TABLES]
    for t in PLAYER_KEYED_TABLES:
        statements += [(f"UPDATE OR IGNORE {t} SET player_id = ? WHERE player_id = ?", (owner, guest)),
                       (f"DELETE FROM {t} WHERE player_id = ?", (guest,))]
    return statements + [("DELETE FROM players WHERE id = ?", (guest,))]


@router.post("/google")
async def sign_in_with_google(req: GoogleSignIn, request: Request, response: Response, player: Player) -> dict:
    """Attaches the Google account to this player. When another player already owns that account,
    this guest's games and progress move to it and the browser switches to that player."""
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(503, "GOOGLE_CLIENT_ID is empty: Google sign-in is off on this server")
    claims = await verify_google(req.credential)
    me = await database.fetch_one("SELECT google_sub FROM players WHERE id = ?", (player,))
    if me and me["google_sub"] not in (None, claims["sub"]):
        raise HTTPException(409, "this browser is signed in to another Google account: sign out first")
    owner = await database.fetch_one("SELECT id FROM players WHERE google_sub = ?", (claims["sub"],))
    if owner and owner["id"] != player:
        await database.transaction(_merge_statements(player, owner["id"]))
        _set_player_cookie(request, response, owner["id"])
        player = owner["id"]
        LOGGER.info("a guest signed in to an existing account; its rows moved")
    await database.execute(
        "INSERT INTO players(id, email, google_sub, signed_in_at) VALUES(?, ?, ?, datetime('now')) "
        "ON CONFLICT(id) DO UPDATE SET email = excluded.email, google_sub = excluded.google_sub, signed_in_at = excluded.signed_in_at",
        (player, claims["email"], claims["sub"]),
    )
    return {"email": claims["email"]}


@router.post("/signout")
async def sign_out(response: Response) -> dict:
    """Forgets the cookie. The account keeps its data; the browser starts again as a new guest."""
    response.delete_cookie(PLAYER_COOKIE)
    return {"ok": True}


@router.delete("")
async def delete_account(response: Response, player: Player) -> dict:
    """Deletes everything stored for this player, the email included, and forgets the cookie."""
    await database.transaction(
        [("DELETE FROM reviews WHERE game_id IN (SELECT id FROM games WHERE player_id = ?)", (player,))]
        + [(f"DELETE FROM {t} WHERE player_id = ?", (player,)) for t in PLAYER_TABLES + PLAYER_KEYED_TABLES]
        + [("DELETE FROM players WHERE id = ?", (player,))]
    )
    response.delete_cookie(PLAYER_COOKIE)
    return {"deleted": True}
