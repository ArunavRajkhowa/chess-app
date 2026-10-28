"""Passwords and reset links: scrypt hashes, HMAC-signed single-use reset tokens, and the per-address
limit on sign-in attempts. Nothing here touches the store; the account router does."""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import asyncio
import secrets
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .settings import settings

LOGGER = logging.getLogger("chess.auth")

MIN_PASSWORD = 8
# scrypt from the standard library: no C extension to build on an arm64 host and no new dependency.
# n=2^15, r=8 costs 32 MiB and about 0.3 s per hash on a dev laptop; the parameters are stored with the hash.
_N, _R, _P = 2**15, 8, 1
_MAXMEM = 64 * 1024 * 1024
# hashes at once: each takes 32 MiB, and the free host has 512 MB next to Stockfish and Maia (a guess).
# Their own threads, so a burst of sign-ins waits on the event loop, not in the pool the store uses.
_HASHERS = ThreadPoolExecutor(2, thread_name_prefix="scrypt")
RESET_HOURS = 2
# A client that fails this often inside the window is refused until the oldest failure ages out.
ATTEMPT_LIMIT, ATTEMPT_WINDOW = 10, 15 * 60
# failures per account from all addresses together: slows guessing spread over many addresses, and is
# high enough that one person mistyping cannot lock the owner out (a guess, not measured)
ACCOUNT_ATTEMPT_LIMIT = 30
SWEEP_AT = 10_000  # tracked keys before aged-out entries are swept, so random keys cannot grow memory


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=_MAXMEM)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


_NOBODY = hash_password(secrets.token_hex(8))  # verified against when the account has no password, so timing is the same


def verify_password(password: str, stored: str | None) -> bool:
    """True when the password made the stored hash; a missing hash still costs one scrypt."""
    _, n, r, p, salt, digest = (stored or _NOBODY).split("$")
    got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), maxmem=_MAXMEM)
    return hmac.compare_digest(got.hex(), digest) and stored is not None


async def hashing(fn, *args):
    """Runs hash_password or verify_password on the hashing threads."""
    return await asyncio.get_running_loop().run_in_executor(_HASHERS, fn, *args)


def secret_key() -> bytes:
    """SECRET_KEY, or the one generated once into secret.key next to the database file."""
    if settings.SECRET_KEY:
        return settings.SECRET_KEY.encode()
    path = Path(settings.DB_PATH).parent / "secret.key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32))
        LOGGER.warning("SECRET_KEY is empty: generated %s", path)
    return path.read_text().strip().encode()


def _sign(payload: str, password_hash: str | None) -> str:
    # The current hash is part of the signature, so a link dies once the password changes: single use.
    return hmac.new(secret_key(), f"{payload}:{password_hash or ''}".encode(), "sha256").hexdigest()


def reset_token(email: str, password_hash: str | None) -> str:
    payload = f"{email}:{int(time.time()) + RESET_HOURS * 3600}"  # the email, never the player id: the id is a credential
    return base64.urlsafe_b64encode(payload.encode()).decode() + "." + _sign(payload, password_hash)


def _parse(token: str) -> tuple[str, str, str] | None:
    """(payload, email, signature) when the token has the shape and has not expired."""
    try:
        encoded, signature = token.split(".")
        payload = base64.urlsafe_b64decode(encoded).decode()
        email, expires = payload.rsplit(":", 1)
        expiry = int(expires)
    except (ValueError, UnicodeDecodeError):
        return None
    return (payload, email, signature) if expiry > time.time() else None


def reset_token_email(token: str) -> str | None:
    """The email a live token names; the caller then checks the signature against that account's hash."""
    parsed = _parse(token)
    return parsed[1] if parsed else None


def reset_token_valid(token: str, password_hash: str | None) -> bool:
    parsed = _parse(token)
    return bool(parsed) and hmac.compare_digest(parsed[2], _sign(parsed[0], password_hash))


_attempts: dict[tuple[str, str], list[float]] = defaultdict(list)  # (bucket, client address) -> failure times


def over_limit(bucket: str, client: str, limit: int = ATTEMPT_LIMIT) -> bool:
    """True once the client has `limit` recorded attempts inside the window. In memory, one process."""
    recent = [t for t in _attempts.get((bucket, client), []) if t > time.time() - ATTEMPT_WINDOW]
    if recent:
        _attempts[bucket, client] = recent
    else:
        _attempts.pop((bucket, client), None)  # spoofed or aged-out addresses keep no entry
    return len(recent) >= limit


def forget_attempt(bucket: str, client: str) -> None:
    """Takes back the latest recorded attempt; an emptied key is removed, since the sweep reads its last time."""
    times = _attempts.get((bucket, client))
    if times:
        times.pop()
    if not times:
        _attempts.pop((bucket, client), None)


def record_attempt(bucket: str, client: str) -> None:
    now = time.time()
    if len(_attempts) >= SWEEP_AT:
        for key in [k for k, times in _attempts.items() if times[-1] <= now - ATTEMPT_WINDOW]:
            del _attempts[key]
    _attempts[bucket, client].append(now)
