"""Errore applicativo con messaggio traducibile: `key` e' il testo inglese (con segnaposto {nome}),
`params` i valori. Il server invia key+params, il client li traduce nella lingua dell'utente."""
from __future__ import annotations

from typing import Any, Dict


class AppError(Exception):
    def __init__(self, key: str, status: int = 400, **params: Any):
        self.key, self.status, self.params = key, status, params
        self.retry_after: int = int(params.pop("retry_after", 0) or 0)     # secondi di attesa (429)
        super().__init__(key.format(**params) if params else key)

    def payload(self) -> Dict[str, Any]:
        out = {"error": str(self), "key": self.key, "params": self.params}
        if getattr(self, "retry_after", None):
            out["retry_after"] = int(self.retry_after)
        return out
