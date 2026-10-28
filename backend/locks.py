"""One asyncio lock per key, kept only while a request holds or waits on it."""
from __future__ import annotations

import asyncio
import weakref


class KeyedLocks:
    def __init__(self) -> None:
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()

    def __getitem__(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = self._locks[key] = asyncio.Lock()
        return lock
