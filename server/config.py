"""Configurazione del server e caricamento della chiave amministratore.

La chiave NON e' nel codice. Viene letta, nell'ordine, da:
  1. variabile d'ambiente AM_ADMIN_KEY
  2. file  server/admin_key.txt   (contiene SOLO la chiave)
  3. file  <cartella dati>/admin_key.txt
Il contenuto puo' essere la chiave in chiaro oppure  sha256:<hex>  (creato con `python -m server hash-key`),
cosi' sul server resta solo l'impronta. Per non pubblicarla: nel .gitignore decommenta la riga
`server/admin_key.txt` quando il progetto va sul server.
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
    return ""                                   # nessuna chiave: la funzione e' disattivata


def key_matches(candidate: str, stored: str) -> bool:
    """Confronto a tempo costante; `stored` puo' essere 'sha256:<hex>'."""
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
    trust_proxy: bool = False                  # True solo dietro Caddy/nginx: usa X-Forwarded-For per l'IP

    def client_ip(self, peer: str, forwarded: Optional[str]) -> str:
        if self.trust_proxy and forwarded:
            return forwarded.split(",")[-1].strip() or peer      # l'ultimo lo aggiunge il nostro proxy
        return peer
