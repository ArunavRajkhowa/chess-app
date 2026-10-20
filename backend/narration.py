"""Narration audio: a sentence becomes an MP3 through Microsoft Edge's free neural voices (the
`edge-tts` client), cached under data/audio by voice and text so every sentence is fetched once.
Optional: when the service is unreachable the browser's own voices speak instead."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re

from .settings import REPO_ROOT, settings

LOGGER = logging.getLogger("chess.narration")
AUDIO_DIR = REPO_ROOT / "data" / "audio"
MAX_TEXT = 600  # one frame's narration; longer text is a bug in the caller, not a sentence to read
RATE = "-6%"  # a touch slower than the default: a coach, not a newsreader
_SAN = re.compile(r"\b([KQRBN])?([a-h])?x?([a-h][1-8])(=[QRBN])?([+#])?\b")
_PIECES = {"K": "king", "Q": "queen", "R": "rook", "B": "bishop", "N": "knight"}


def audio_path(text: str, voice: str):
    key = hashlib.sha1(f"{voice}|{RATE}|{text}".encode()).hexdigest()[:20]
    return AUDIO_DIR / f"{key}.mp3"


def spoken_text(text: str) -> str:
    """Move notation the way a coach says it: 'Nxe5+' becomes 'knight takes e5, check'; squares get a
    space between file and rank so the voice does not read 'e4' as a word."""
    def one(m: re.Match) -> str:
        piece, frm, to, promo, suffix = m.groups()
        words = []
        if piece:
            words.append(_PIECES[piece])
        if frm:
            words.append(frm)
        if "x" in m.group(0):
            words.append("takes")
        words.append(f"{to[0]} {to[1]}")
        if promo:
            words.append(f"promotes to a {_PIECES[promo[1]]}")
        out = " ".join(words)
        return out + (", checkmate" if suffix == "#" else ", check" if suffix == "+" else "")

    text = text.replace("O-O-O", "castles queenside").replace("O-O", "castles kingside")
    return _SAN.sub(one, text)


async def synthesize(text: str, voice: str | None = None) -> bytes | None:
    """The MP3 for a sentence, from the cache or freshly made; None when narration is off or the service fails."""
    if not settings.NARRATION_TTS:
        return None
    voice = voice or settings.NARRATION_VOICE
    text = text.strip()
    if not text or len(text) > MAX_TEXT:
        return None
    path = audio_path(text, voice)
    if path.exists():
        return path.read_bytes()
    try:
        import edge_tts
    except ImportError:
        LOGGER.warning("edge-tts is not installed: narration falls back to the browser's voices")
        return None
    try:
        communicate = edge_tts.Communicate(spoken_text(text), voice, rate=RATE)
        chunks: list[bytes] = []
        async with asyncio.timeout(20):
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
    except Exception:  # boundary: the voice service is optional; the browser speaks instead
        LOGGER.warning("narration synthesis failed for %d characters with voice %s", len(text), voice, exc_info=True)
        return None
    data = b"".join(chunks)
    if not data:
        return None
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data
