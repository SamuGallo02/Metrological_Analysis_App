"""Attempt limit: after N errors the key stays blocked for a while. Never blocks the server:
whoever is blocked immediately gets a 429 error with the remaining time and other requests carry on."""
from __future__ import annotations

import threading
import time
from typing import Dict, Tuple

from common.errors import AppError


class Throttle:
    def __init__(self, max_fails: int, lock_seconds: int, max_entries: int = 10_000):
        self.max_fails, self.lock_seconds, self.max_entries = max_fails, lock_seconds, max_entries
        self._d: Dict[str, Tuple[int, float]] = {}
        self._lock = threading.Lock()

    def check(self, *ids: str) -> None:
        """Raises AppError 429 (with retry_after) if one of the identifiers is blocked."""
        now = time.time()
        with self._lock:
            for i in ids:
                until = self._d.get(i, (0, 0.0))[1]
                if until > now:
                    raise AppError("Too many attempts with the access key: try again in {minutes} min.", 429,
                                   minutes=max(1, int((until - now + 59) // 60)), scope="key", retry_after=int(until - now) + 1)

    def fail(self, *ids: str) -> bool:
        """Records an error; True if it triggered the block."""
        now = time.time()
        locked = False
        with self._lock:
            if len(self._d) > self.max_entries:                       # cleanup: expired
                self._d = {k: v for k, v in self._d.items() if v[1] > now}
            for i in ids:
                n, until = self._d.get(i, (0, 0.0))
                if until and until <= now:
                    n = 0
                n += 1
                if n >= self.max_fails:
                    self._d[i], locked = (0, now + self.lock_seconds), True
                else:
                    self._d[i] = (n, 0.0)
        return locked

    def reset(self, *ids: str) -> None:
        with self._lock:
            for i in ids:
                self._d.pop(i, None)
