"""User data saved locally (a copy of the server's), in a per-user system folder.

  settings.json     server address, last user, language
  users.json        profiles that have already logged in on this computer: name, role, PBKDF2 password verifier
                    (never the password) -> allows access without network
  session.json      server access token
  profiles.json     last downloaded profile of each user + chosen local folders
  users_cache.json  last user list seen by an administrator (offline consultation)
The local verifier is valid only for this computer; the server remains the authority.
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
        """default_folders: default local folders by key (photos, models, datasets, results);
        the application passes its own, those not specified live in <data>/data/<name>."""
        self.default_folders = {k: str(v) for k, v in (default_folders or {}).items()}
        self.dir = Path(folder) if folder else user_data_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self._settings = Settings(self.dir)

    # ---- settings ------------------------------------------------------
    def settings(self) -> Dict[str, Any]:
        return self._settings.all()

    def update_settings(self, **kw: Any) -> None:
        self._settings.update(**kw)

    # ---- local profiles (offline login) ----------------------------------
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
        if not rec:                                     # any server address: offline, only this computer's copy counts
            return None
        if not verify_password(password or "", rec["salt"], rec["pw_hash"]):
            return None
        return {"username": rec["username"], "role": rec["role"], **self.profile(rec["username"])}

    def forget_user(self, username: str) -> None:
        users = self._users()
        users.pop(username.lower(), None)
        write_json(self.dir / F_USERS, users)

    # ---- session ----------------------------------------------------------
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

    # ---- profile and local folders (per user) -----------------------------
    def _profiles(self) -> Dict[str, Dict[str, Any]]:
        return read_json(self.dir / F_PROFILES, {})

    def profile(self, username: str) -> Dict[str, Any]:
        return dict(self._profiles().get(username.lower(), {}).get("profile", {}))

    def save_profile(self, username: str, profile: Dict[str, Any]) -> None:
        all_ = self._profiles()
        all_.setdefault(username.lower(), {})["profile"] = profile
        write_json(self.dir / F_PROFILES, all_)

    def folders(self, username: str) -> Dict[str, str]:
        """The user's local folders; those not chosen use the application defaults."""
        chosen = self._profiles().get((username or "guest").lower(), {}).get("folders", {})
        return {k: chosen.get(k) or self.default_folders.get(k) or str(self.dir / "data" / k) for k in LOCAL_FOLDERS}

    def set_folders(self, username: str, folders: Dict[str, str]) -> None:
        all_ = self._profiles()
        all_.setdefault((username or "guest").lower(), {})["folders"] = {
            k: str(v) for k, v in folders.items() if k in LOCAL_FOLDERS and v}
        write_json(self.dir / F_PROFILES, all_)

    # ---- copy of the user list (administrator) --------------------------
    def save_users_snapshot(self, users: List[Dict[str, Any]]) -> None:
        write_json(self.dir / F_USERS_CACHE, {"saved": time.time(), "users": users})

    def users_snapshot(self) -> Dict[str, Any]:
        return read_json(self.dir / F_USERS_CACHE, {"saved": None, "users": []})
