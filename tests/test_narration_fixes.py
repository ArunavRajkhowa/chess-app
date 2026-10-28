"""Narration cache: new sentences stop being written to disk once the cache is full."""
from __future__ import annotations

import sys
import types

from backend import narration


class _Voice:
    def __init__(self, text, voice, rate):
        pass

    async def stream(self):
        yield {"type": "audio", "data": b"mp3"}


def test_full_cache_still_speaks_but_writes_nothing(event_loop, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=_Voice))
    monkeypatch.setattr(narration.settings, "NARRATION_TTS", True)
    monkeypatch.setattr(narration, "AUDIO_DIR", tmp_path)
    monkeypatch.setattr(narration, "MAX_CACHED_FILES", 2)
    for word in ("one", "two", "three"):
        assert event_loop.run_until_complete(narration.synthesize(f"Sentence {word}.")) == b"mp3"
    assert len(list(tmp_path.glob("*.mp3"))) == 2
