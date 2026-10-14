"""General request limit per client address (sliding window). Protects a server exposed to a network."""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict

from common.errors import AppError


class RateLimiter:
    def __init__(self, max_requests: int, window: float = 60.0, max_entries: int = 10_000):
        self.max_requests, self.window, self.max_entries = max_requests, window, max_entries
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, ident: str) -> None:
        """Counts a request; raises AppError 429 (with retry_after) when the address exceeds the limit."""
        if self.max_requests <= 0:
            return                                              # 0 = no limit
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > self.max_entries:              # cleanup of idle addresses
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < self.window}
            q = self._hits.setdefault(ident, deque())
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.max_requests:
                wait = int(self.window - (now - q[0])) + 1
                raise AppError("Too many requests: try again in {seconds} s.", 429, seconds=wait, scope="rate",
                               retry_after=wait)
            q.append(now)
