"""Dati utente salvati in locale (copia di quelli sul server), in una cartella per utente del sistema.

  settings.json     indirizzo del server, ultimo utente, lingua
  users.json        profili gia' entrati su questo computer: nome, ruolo, verificatore PBKDF2 della password
                    (mai la password) -> permette l'accesso senza rete
  session.json      token di accesso al server
  profiles.json     ultimo profilo scaricato di ogni utente + cartelle locali scelte
  users_cache.json  ultima lista utenti vista da un amministratore (consultazione offline)
Il verificatore locale vale solo per questo computer; il server resta l'autorita'.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.paths import user_data_dir
from common.security import hash_password, verify_password
from common.settings import Settings, read_json, write_json

from .params import F_PROFILES, F_SESSION, F_USERS, F_USERS_CACHE, LOCAL_FOLDERS


class LocalStore:
    def __init__(self, folder: Optional[Path] = None, default_folders: Optional[Dict[str, Any]] = None):
        """default_folders: cartelle locali predefinite per chiave (photos, models, datasets, results);
        l'applicazione passa le proprie, quelle non indicate stanno in <dati>/data/<nome>."""
        self.default_folders = {k: str(v) for k, v in (default_folders or {}).items()}
        self.dir = Path(folder) if folder else user_data_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self._settings = Settings(self.dir)

    # ---- impostazioni ------------------------------------------------------
    def settings(self) -> Dict[str, Any]:
        return self._settings.all()

    def update_settings(self, **kw: Any) -> None:
        self._settings.update(**kw)

    # ---- profili locali (accesso offline) ----------------------------------
    def _users(self) -> Dict[str, Dict[str, Any]]:
        return read_json(self.dir / F_USERS, {})

    def remember_user(self, user: Dict[str, Any], password: str, server_url: str) -> None:
        salt, h = hash_password(password)
        users = self._users()
        users[user["username"].lower()] = {"username": user["username"], "role": user["role"], "salt": salt,
                                           "pw_hash": h, "server": server_url, "last_login": time.time()}
        write_json(self.dir / F_USERS, users)

    def verify_offline(self, username: str, password: str, server_url: str) -> Optional[Dict[str, Any]]:
        rec = self._users().get((username or "").strip().lower())
        if not rec or rec.get("server") != server_url:
            return None
        if not verify_password(password or "", rec["salt"], rec["pw_hash"]):
            return None
        return {"username": rec["username"], "role": rec["role"], **self.profile(rec["username"])}

    def forget_user(self, username: str) -> None:
        users = self._users()
        users.pop(username.lower(), None)
        write_json(self.dir / F_USERS, users)

    # ---- sessione ----------------------------------------------------------
    def save_session(self, token: str, user: Dict[str, Any], server_url: str) -> None:
        write_json(self.dir / F_SESSION, {"token": token, "user": user, "server": server_url})

    def load_session(self) -> Optional[Dict[str, Any]]:
        s = read_json(self.dir / F_SESSION, None)
        return s if s and s.get("token") else None

    def clear_session(self) -> None:
        try:
            (self.dir / F_SESSION).unlink()
        except OSError:
            pass

    # ---- profilo e cartelle locali (per utente) -----------------------------
    def _profiles(self) -> Dict[str, Dict[str, Any]]:
        return read_json(self.dir / F_PROFILES, {})

    def profile(self, username: str) -> Dict[str, Any]:
        return dict(self._profiles().get(username.lower(), {}).get("profile", {}))

    def save_profile(self, username: str, profile: Dict[str, Any]) -> None:
        all_ = self._profiles()
        all_.setdefault(username.lower(), {})["profile"] = profile
        write_json(self.dir / F_PROFILES, all_)

    def folders(self, username: str) -> Dict[str, str]:
        """Cartelle locali dell'utente; quelle non scelte usano i predefiniti dell'applicazione."""
        chosen = self._profiles().get((username or "guest").lower(), {}).get("folders", {})
        return {k: chosen.get(k) or self.default_folders.get(k) or str(self.dir / "data" / k) for k in LOCAL_FOLDERS}

    def set_folders(self, username: str, folders: Dict[str, str]) -> None:
        all_ = self._profiles()
        all_.setdefault((username or "guest").lower(), {})["folders"] = {
            k: str(v) for k, v in folders.items() if k in LOCAL_FOLDERS and v}
        write_json(self.dir / F_PROFILES, all_)

    # ---- copia della lista utenti (amministratore) --------------------------
    def save_users_snapshot(self, users: List[Dict[str, Any]]) -> None:
        write_json(self.dir / F_USERS_CACHE, {"saved": time.time(), "users": users})

    def users_snapshot(self) -> Dict[str, Any]:
        return read_json(self.dir / F_USERS_CACHE, {"saved": None, "users": []})
