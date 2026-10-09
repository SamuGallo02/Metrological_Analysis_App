"""Sessione corrente: chi e' entrato, con quale ruolo e se il server e' raggiungibile."""
from __future__ import annotations

from typing import Any, Dict, Optional

from common.params import PROFILE_FIELDS, ROLE_SERVER, ROLE_USER

from .api import ApiClient, ApiError, OfflineError, is_secure, normalize_url
from .params import PERMISSIONS, SERVER_SIDE_PREFIXES
from .store import LocalStore


class Session:
    def __init__(self, store: Optional[LocalStore] = None):
        self.store = store or LocalStore()
        self.client: Optional[ApiClient] = None
        self.user: Optional[Dict[str, Any]] = None
        self.online = False
        self.server_url = self.store.settings().get("server_url", "")

    # ---- stato -------------------------------------------------------------
    @property
    def logged_in(self) -> bool:
        return self.user is not None

    @property
    def username(self) -> str:
        return (self.user or {}).get("username", "")

    @property
    def role(self) -> str:
        return (self.user or {}).get("role", "")

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_SERVER

    @property
    def is_guest(self) -> bool:
        return bool((self.user or {}).get("guest"))

    def can(self, action: str) -> bool:
        if not self.logged_in:
            return False
        if self.is_guest:                           # senza account: solo analisi e training in locale
            return action in ("analysis.run", "training.run")
        if self.role not in PERMISSIONS.get(action, ()):
            return False
        return self.online if action.startswith(SERVER_SIDE_PREFIXES) else True   # sul server serve la rete

    def local_folders(self) -> Dict[str, str]:
        return self.store.folders("" if self.is_guest else self.username)

    # ---- accesso -----------------------------------------------------------
    def login(self, username: str, password: str, server_url: str, allow_offline: bool = True,
              key: str = "") -> str:
        """Ritorna 'online' oppure 'offline'. Solleva ApiError se credenziali o chiave sono errate
        (con retry_after se la chiave e' bloccata)."""
        url = normalize_url(server_url)
        client = ApiClient(url)
        try:
            user = client.login(username, password, key)
        except OfflineError:
            if not allow_offline:
                raise
            u = self.store.verify_offline(username, password, url)
            if u is None:
                raise OfflineError("Server unreachable and no saved local access for this user.")
            self.client, self.user, self.online, self.server_url = None, u, False, url
            return "offline"
        self.client, self.user, self.online, self.server_url = client, user, True, url
        self.store.remember_user(user, password, url)
        self.store.save_profile(user["username"], _profile_of(user))
        self.store.update_settings(server_url=url, last_user=user["username"])
        self.store.save_session(client.token, user, url)
        return "online"

    def register(self, username: str, password: str, server_url: str, key: str = "") -> None:
        ApiClient(normalize_url(server_url)).register(username, password, key)

    def start_offline(self) -> None:
        """Entra senza account: nessun accesso al server, analisi e training restano disponibili."""
        self.client, self.online = None, False
        self.user = {"username": "offline", "role": ROLE_USER, "guest": True}

    def resume(self) -> bool:
        """Riprende la sessione salvata (token). Se il server non risponde entra in modo offline."""
        s = self.store.load_session()
        if not s:
            return False
        url = s["server"]
        client = ApiClient(url, s["token"])
        try:
            user = client.me()
        except OfflineError:
            self.client, self.user, self.online, self.server_url = None, s["user"], False, url
            return True
        except ApiError:                            # token scaduto o account disattivato
            self.store.clear_session()
            return False
        self.client, self.user, self.online, self.server_url = client, user, True, url
        self.store.save_session(client.token, user, url)
        return True

    def reconnect(self) -> bool:
        """Riprova a collegarsi al server con il token salvato (dopo un periodo offline)."""
        s = self.store.load_session()
        if not s:
            return False
        client = ApiClient(s["server"], s["token"])
        try:
            self.user = client.me()
        except ApiError:
            return False
        self.client, self.online = client, True
        return True

    def logout(self) -> None:
        if self.client and self.online:
            try:
                self.client.logout()
            except ApiError:
                pass
        self.store.clear_session()
        self.client, self.user, self.online = None, None, False

    # ---- profilo -----------------------------------------------------------
    def profile(self) -> Dict[str, Any]:
        """Dati del profilo (dal server se online, altrimenti l'ultima copia locale)."""
        if self.online and self.client:
            self.user = self.client.me()
            self.store.save_profile(self.username, _profile_of(self.user))
        return _profile_of(self.user or {}) or self.store.profile(self.username)

    def save_profile(self, **fields: str) -> Dict[str, Any]:
        if not (self.online and self.client) or self.is_guest:
            raise OfflineError("Profile changes need a connection to the server.")
        self.user = self.client.update_profile(**fields)
        self.store.save_profile(self.username, _profile_of(self.user))
        return self.user

    def insecure_warning(self) -> bool:
        return bool(self.server_url) and not is_secure(self.server_url)


def _profile_of(user: Dict[str, Any]) -> Dict[str, Any]:
    return {f: user[f] for f in PROFILE_FIELDS if f in user}
