"""A small sliding-window rate limiter, in memory, per process.

Cue deploys as a single uvicorn process, so there's no shared store to
coordinate with — a dict of deques is the honest tool. Each key (one
visitor) gets `limit` calls per `window_seconds`; a blocked call reports
how long until the oldest counted call ages out, so the 429 can carry a
truthful Retry-After. Blocked calls consume no budget: hammering while
blocked never pushes recovery further away.
"""

import math
import time
from collections import deque


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._calls: dict[str, deque] = {}

    def allow(self, key: str, now: float | None = None) -> tuple[bool, int]:
        """One attempted call by `key`. Returns (allowed, retry_after_seconds);
        retry_after is 0 when allowed."""
        if now is None:
            now = time.monotonic()
        calls = self._calls.setdefault(key, deque())
        while calls and calls[0] <= now - self.window:
            calls.popleft()
        if len(calls) >= self.limit:
            return False, max(1, math.ceil(calls[0] + self.window - now))
        calls.append(now)
        return True, 0
