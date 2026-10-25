"""Accounts: a guest is a random id in the httpOnly `player` cookie; an account (password or Google)
is reached only through a random `session` token that a `sessions` row maps to it.
The id is a secret: no response body ever carries it."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import secrets
from typing import Annotated

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import auth, mail
from ..settings import settings
from ..storage.db import database

LOGGER = logging.getLogger("chess.account")
router = APIRouter(prefix="/api/account", tags=["account"])

PLAYER_COOKIE = "player"
SESSION_COOKIE = "session"
COOKIE_DAYS = 400  # the longest lifetime Chrome keeps a cookie
_PLAYER_ID = re.compile(r"[0-9a-f]{32}")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
GOOGLE_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
WRONG_SIGN_IN = "wrong email or password"  # one message for both, so the form never confirms an address
SIGNED_IN = "this browser is already signed in: sign out first"
LOCAL_HOSTS = ("localhost", "127.0.0.1")

# Every table with a player_id column. A guest who signs in to an existing account brings these rows along.
PLAYER_TABLES = ("games", "puzzle_attempts", "events", "sessions", "player_plans")
# Per-player tables with one row per key: when the guest and the account both have a key, the account's row wins.
PLAYER_KEYED_TABLES = ("player_lessons", "player_values", "player_reviews")

_sessions: dict[str, str] = {}  # token hash -> player id, so a signed-in request costs no store read


def _set_cookie(request: Request, response: Response, name: str, value: str) -> None:
    response.set_cookie(name, value, max_age=COOKIE_DAYS * 86400, httponly=True, samesite="lax",
                        secure=request.url.scheme == "https")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def current_player(request: Request, response: Response) -> str:
    """The caller's player id: from the session, else the guest cookie; without either, a new guest."""
    token = request.cookies.get(SESSION_COOKIE, "")
    if token:
        key = _token_hash(token)
        if key not in _sessions:
            row = await database.fetch_one("SELECT player_id FROM sessions WHERE token_hash = ?", (key,))
            if row:
                _sessions[key] = row["player_id"]
        if key in _sessions:
            return _sessions[key]
        response.delete_cookie(SESSION_COOKIE)  # signed out elsewhere: carry on as a guest
    player_id = request.cookies.get(PLAYER_COOKIE, "")
    if _PLAYER_ID.fullmatch(player_id) and not await database.fetch_one(
            "SELECT 1 FROM players WHERE id = ? AND (email IS NOT NULL OR password_hash IS NOT NULL OR google_sub IS NOT NULL)",
            (player_id,)):
        return player_id  # a guest; an account's id is no credential, only its session is
    player_id = secrets.token_hex(16)
    await database.execute("INSERT INTO players(id) VALUES(?)", (player_id,))
    _set_cookie(request, response, PLAYER_COOKIE, player_id)
    return player_id


Player = Annotated[str, Depends(current_player)]


class GoogleSignIn(BaseModel):
    credential: str  # the ID token that Google's button hands the page


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=auth.MIN_PASSWORD)


class PasswordChange(BaseModel):
    current: str
    new: str = Field(min_length=auth.MIN_PASSWORD)


class ResetRequest(BaseModel):
    email: str = Field(max_length=254)


class ResetConfirm(BaseModel):
    token: str
    password: str = Field(min_length=auth.MIN_PASSWORD)


class SignOut(BaseModel):
    everywhere: bool = False


@router.get("")
async def account(player: Player) -> dict:
    """Who is playing. The browser calls it first, so a new visitor has a cookie before anything else."""
    await database.execute("INSERT OR IGNORE INTO players(id) VALUES(?)", (player,))  # a cookie older than this database
    row = await database.fetch_one("SELECT email, password_hash FROM players WHERE id = ?", (player,))
    return {"email": row["email"], "has_password": row["password_hash"] is not None,
            "google_client_id": settings.GOOGLE_CLIENT_ID or None}


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


async def _start_session(request: Request, response: Response, guest: str, owner: str) -> None:
    """Signs the browser in as owner: a guest's rows move to the account, and a session replaces the guest cookie."""
    if guest != owner:
        await database.transaction(_merge_statements(guest, owner))
        LOGGER.info("a guest signed in to an existing account; its rows moved")
    token = secrets.token_urlsafe(32)
    await database.execute("INSERT INTO sessions(token_hash, player_id) VALUES(?, ?)", (_token_hash(token), owner))
    _set_cookie(request, response, SESSION_COOKIE, token)
    response.delete_cookie(PLAYER_COOKIE)


async def _end_sessions(player: str, keep: str | None = None) -> None:
    """Deletes the player's sessions, all of them or all but the one with the given token."""
    rows = await database.fetch_all("SELECT token_hash FROM sessions WHERE player_id = ?", (player,))
    kept = _token_hash(keep) if keep else None
    stale = [r["token_hash"] for r in rows if r["token_hash"] != kept]
    for key in stale:
        _sessions.pop(key, None)
    await database.transaction([("DELETE FROM sessions WHERE token_hash = ?", (k,)) for k in stale])


def _client(request: Request) -> str:
    """The address the rate limits key on: the rightmost X-Forwarded-For entry, which the platform's proxy
    appended (the client chooses the leftmost one), else the socket's peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.rsplit(",", 1)[-1].strip()
    return request.client.host if request.client else "?"


def _limit(bucket: str, request: Request, what: str) -> None:
    """Counts one attempt from the caller's address; raises 429 once the address is over the limit."""
    if auth.over_limit(bucket, _client(request)):
        raise HTTPException(429, f"too many {what}: wait {auth.ATTEMPT_WINDOW // 60} minutes")
    auth.record_attempt(bucket, _client(request))


def _email(value: str) -> str:
    email = value.strip().lower()
    if not _EMAIL.fullmatch(email):
        raise HTTPException(422, f"{value!r} is not an email address")
    return email


@router.post("/google")
async def sign_in_with_google(req: GoogleSignIn, request: Request, response: Response, player: Player) -> dict:
    """Attaches the Google account to this player. When another player already owns that account,
    this guest's games and progress move to it and the browser switches to that player."""
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(503, "GOOGLE_CLIENT_ID is empty: Google sign-in is off on this server")
    claims = await verify_google(req.credential)
    email = claims["email"].lower()
    me = await database.fetch_one("SELECT email, password_hash, google_sub FROM players WHERE id = ?", (player,))
    if me and (me["email"] or me["password_hash"] or me["google_sub"]) and me["google_sub"] != claims["sub"]:
        raise HTTPException(409, SIGNED_IN)
    owner = await database.fetch_one("SELECT id FROM players WHERE google_sub = ?", (claims["sub"],))
    if not owner and await database.fetch_one("SELECT 1 FROM players WHERE email = ? AND id != ?", (email, player)):
        # An address someone signed up with a password is not proven theirs; the reset link to that address is.
        raise HTTPException(409, "an account with this email signs in with a password: use it, or reset the password")
    owner_id = owner["id"] if owner else player
    await database.execute(
        "INSERT INTO players(id, email, google_sub, signed_in_at) VALUES(?, ?, ?, datetime('now')) "
        "ON CONFLICT(id) DO UPDATE SET email = excluded.email, google_sub = excluded.google_sub, signed_in_at = excluded.signed_in_at",
        (owner_id, email, claims["sub"]),
    )
    await _start_session(request, response, player, owner_id)
    return {"email": email}


@router.post("/signup")
async def sign_up(req: Credentials, request: Request, response: Response, player: Player) -> dict:
    """Makes this guest an account with an email and a password. The password is at least 8 characters."""
    _limit("signup", request, "sign-up attempts")
    email = _email(req.email)
    me = await database.fetch_one("SELECT email FROM players WHERE id = ?", (player,))
    if me and me["email"]:
        raise HTTPException(409, SIGNED_IN)
    # Sign-up must say an address is taken, so it reveals that an account exists (rate-limited above);
    # sign-in and reset give one answer for every address.
    if await database.fetch_one("SELECT 1 FROM players WHERE email = ?", (email,)):
        raise HTTPException(409, "an account with this email exists: sign in, or reset the password")
    await database.execute(
        "INSERT INTO players(id, email, password_hash, signed_in_at) VALUES(?, ?, ?, datetime('now')) "
        "ON CONFLICT(id) DO UPDATE SET email = excluded.email, password_hash = excluded.password_hash, signed_in_at = excluded.signed_in_at",
        (player, email, await asyncio.to_thread(auth.hash_password, req.password)),
    )
    await _start_session(request, response, player, player)
    return {"email": email}


@router.post("/signin")
async def sign_in(req: Credentials, request: Request, response: Response, player: Player) -> dict:
    """Signs in with email and password; the guest's games and progress move to the account.
    After 10 failures from one address in 15 minutes, the address waits."""
    if auth.over_limit("signin", _client(request)):
        raise HTTPException(429, f"too many sign-in attempts: wait {auth.ATTEMPT_WINDOW // 60} minutes")
    email = _email(req.email)
    owner = await database.fetch_one("SELECT id, password_hash FROM players WHERE email = ? AND password_hash IS NOT NULL", (email,))
    if not await asyncio.to_thread(auth.verify_password, req.password, owner["password_hash"] if owner else None):
        auth.record_attempt("signin", _client(request))
        raise HTTPException(401, WRONG_SIGN_IN)
    me = await database.fetch_one("SELECT email FROM players WHERE id = ?", (player,))
    if me and me["email"] and player != owner["id"]:
        raise HTTPException(409, SIGNED_IN)
    await database.execute("UPDATE players SET signed_in_at = datetime('now') WHERE id = ?", (owner["id"],))
    await _start_session(request, response, player, owner["id"])
    return {"email": email}


@router.post("/password")
async def change_password(req: PasswordChange, request: Request, player: Player) -> dict:
    """Sets a new password after checking the current one, and signs out every other device."""
    me = await database.fetch_one("SELECT password_hash FROM players WHERE id = ?", (player,))
    if not me or not await asyncio.to_thread(auth.verify_password, req.current, me["password_hash"]):
        raise HTTPException(401, "the current password is wrong")
    new_hash = await asyncio.to_thread(auth.hash_password, req.new)
    await database.execute("UPDATE players SET password_hash = ? WHERE id = ?", (new_hash, player))
    await _end_sessions(player, keep=request.cookies.get(SESSION_COOKIE))
    return {"ok": True}


@router.post("/reset")
async def request_reset(req: ResetRequest, request: Request, background: BackgroundTasks) -> dict:
    """Mails a reset link when an account has the address; the answer and its speed are the same either way.
    The link base is PUBLIC_URL; the Host header is used only for a request to localhost."""
    _limit("reset", request, "reset requests")
    email = _email(req.email)
    owner = await database.fetch_one("SELECT password_hash FROM players WHERE email = ?", (email,))
    local = request.url.hostname in LOCAL_HOSTS
    base = settings.PUBLIC_URL.rstrip("/") or (str(request.base_url).rstrip("/") if local else "")
    if owner and not base:
        LOGGER.warning("PUBLIC_URL is empty and the request came to host %s: reset mail not sent", request.url.hostname)
    elif owner:
        link = f"{base}/settings?reset={auth.reset_token(email, owner['password_hash'])}"
        background.add_task(mail.send, email, "Chess Coach: reset your password",  # after the response
                            f"Open this link within {auth.RESET_HOURS} hours to choose a new password:\n{link}\n")
    return {"ok": True}


@router.post("/reset/confirm")
async def confirm_reset(req: ResetConfirm, request: Request, response: Response, player: Player) -> dict:
    """Sets the password named by a live reset link, signs out every device, and signs this one in."""
    email = auth.reset_token_email(req.token)
    owner = await database.fetch_one("SELECT id, email, password_hash FROM players WHERE email = ?", (email,)) if email else None
    if not owner or not auth.reset_token_valid(req.token, owner["password_hash"]):
        raise HTTPException(401, "this reset link is not valid any more: ask for a new one")
    await database.execute("UPDATE players SET password_hash = ?, signed_in_at = datetime('now') WHERE id = ?",
                           (await asyncio.to_thread(auth.hash_password, req.password), owner["id"]))
    await _end_sessions(owner["id"])
    me = await database.fetch_one("SELECT email FROM players WHERE id = ?", (player,))
    signed_in_as_another = bool(me and me["email"]) and player != owner["id"]  # that account is not merged away
    await _start_session(request, response, owner["id"] if signed_in_as_another else player, owner["id"])
    return {"email": owner["email"]}


@router.post("/signout")
async def sign_out(request: Request, response: Response, player: Player, req: SignOut | None = None) -> dict:
    """Ends this session, or every session of the account. The account keeps its data; the browser starts again as a new guest."""
    token = request.cookies.get(SESSION_COOKIE)
    if req and req.everywhere:
        await _end_sessions(player)
    elif token:
        _sessions.pop(_token_hash(token), None)
        await database.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(PLAYER_COOKIE)
    return {"ok": True}


@router.delete("")
async def delete_account(response: Response, player: Player) -> dict:
    """Deletes everything stored for this player, the email included, and forgets the cookie."""
    await _end_sessions(player)
    await database.transaction(
        [("DELETE FROM reviews WHERE game_id IN (SELECT id FROM games WHERE player_id = ?)", (player,))]
        + [(f"DELETE FROM {t} WHERE player_id = ?", (player,)) for t in PLAYER_TABLES + PLAYER_KEYED_TABLES]
        + [("DELETE FROM players WHERE id = ?", (player,))]
    )
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(PLAYER_COOKIE)
    return {"deleted": True}
