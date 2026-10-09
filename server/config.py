"""Server configuration and loading of the administrator key.

The key is NOT in the code. It is read, in order, from:
  1. environment variable AM_ADMIN_KEY
  2. file  server/admin_key.txt   (contains ONLY the key)
  3. file  <data folder>/admin_key.txt
The content can be the plain key or  sha256:<hex>  (created with `python -m server hash-key`),
so that only the fingerprint stays on the server. To avoid publishing it: in .gitignore uncomment the line
`server/admin_key.txt` when the project goes on the server.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .params import ADMIN_KEY_FILES

HERE = Path(__file__).resolve().parent


def load_admin_key(data_dir: Path) -> str:
    env = os.environ.get("AM_ADMIN_KEY")
    if env is not None:
        return env.strip()
    for folder in (HERE, Path(data_dir)):
        for name in ADMIN_KEY_FILES:
            f = folder / name
            try:
                return f.read_text(encoding="utf-8").strip()
            except OSError:
                continue
    return ""                                   # no key: the feature is disabled


def key_matches(candidate: str, stored: str) -> bool:
    """Constant-time comparison; `stored` may be 'sha256:<hex>'."""
    if not stored or not candidate:
        return False
    if stored.lower().startswith("sha256:"):
        digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
        return hmac.compare_digest(digest, stored[7:].strip().lower())
    return hmac.compare_digest(candidate.encode("utf-8"), stored.encode("utf-8"))


def hash_key(key: str) -> str:
    return "sha256:" + hashlib.sha256(key.encode("utf-8")).hexdigest()


@dataclass
class ServerConfig:
    data_dir: Path
    allow_register: bool = True
    admin_key: str = ""
    trust_proxy: bool = False                  # True only behind Caddy/nginx: uses X-Forwarded-For for the IP

    def client_ip(self, peer: str, forwarded: Optional[str]) -> str:
        if self.trust_proxy and forwarded:
            return forwarded.split(",")[-1].strip() or peer      # the last one is added by our proxy
        return peer
