"""Application error with a translatable message: `key` is the English text (with {name} placeholders),
`params` the values. The server sends key+params, the client translates them into the user's language."""
from __future__ import annotations

from typing import Any, Dict


class AppError(Exception):
    def __init__(self, key: str, status: int = 400, **params: Any):
        self.key, self.status, self.params = key, status, params
        self.retry_after: int = int(params.pop("retry_after", 0) or 0)     # seconds to wait (429)
        super().__init__(key.format(**params) if params else key)

    def payload(self) -> Dict[str, Any]:
        out = {"error": str(self), "key": self.key, "params": self.params}
        if getattr(self, "retry_after", None):
            out["retry_after"] = int(self.retry_after)
        return out
