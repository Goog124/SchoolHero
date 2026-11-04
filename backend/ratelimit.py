"""Tiny in-process sliding-window rate limiter.

State lives in memory, which is enough for a single-process deployment; a
restart simply clears the counters. Keys include the database path so
independent databases (tests) never share counters.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _trim(self, key: str, window: float, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and now - hits[0] > window:
            hits.popleft()
        return hits

    def count(self, key: str, window: float) -> int:
        with self._lock:
            return len(self._trim(key, window, time.monotonic()))

    def add(self, key: str, window: float) -> None:
        with self._lock:
            now = time.monotonic()
            self._trim(key, window, now).append(now)

    def hit(self, key: str, limit: int, window: float) -> bool:
        """Record a hit; return False (and do not record) when over the limit."""
        with self._lock:
            now = time.monotonic()
            hits = self._trim(key, window, now)
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()
