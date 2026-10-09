"""Limite ai tentativi: dopo N errori la chiave resta bloccata per un po'. Non blocca mai il server:
chi e' bloccato riceve subito un errore 429 con il tempo residuo e le altre richieste proseguono."""
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
        """Solleva AppError 429 (con retry_after) se uno degli identificativi e' bloccato."""
        now = time.time()
        with self._lock:
            for i in ids:
                until = self._d.get(i, (0, 0.0))[1]
                if until > now:
                    raise AppError("Too many attempts with the access key: try again in {minutes} min.", 429,
                                   minutes=max(1, int((until - now + 59) // 60)), scope="key", retry_after=int(until - now) + 1)

    def fail(self, *ids: str) -> bool:
        """Registra un errore; True se ha fatto scattare il blocco."""
        now = time.time()
        locked = False
        with self._lock:
            if len(self._d) > self.max_entries:                       # pulizia: scaduti
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
