"""Archivio utenti, sessioni e registro attivita' (SQLite)."""
from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.errors import AppError
from common.params import ROLE_SERVER, ROLE_USER, ROLES
from common.security import (hash_password, new_token, token_digest, validate_password, validate_username,
                             verify_password)

from .params import DEFAULT_QUOTA_MB, LOGIN_LOCK_SECONDS, LOGIN_MAX_FAILS, PROFILE_FIELDS, TOKEN_TTL

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_COLUMNS = {"full_name": "TEXT NOT NULL DEFAULT ''", "email": "TEXT NOT NULL DEFAULT ''",
            "organization": "TEXT NOT NULL DEFAULT ''", "phone": "TEXT NOT NULL DEFAULT ''",
            "bio": "TEXT NOT NULL DEFAULT ''", "quota_mb": "INTEGER NOT NULL DEFAULT 0"}


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._c() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS users(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL UNIQUE COLLATE NOCASE,
              role TEXT NOT NULL, salt TEXT NOT NULL, pw_hash TEXT NOT NULL,
              active INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL,
              last_login REAL, failed INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS tokens(
              digest TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires REAL NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS events(
              id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, username TEXT NOT NULL,
              action TEXT NOT NULL, area TEXT, path TEXT, size INTEGER);
            """)
            have = {r[1] for r in c.execute("PRAGMA table_info(users)")}
            for col, decl in _COLUMNS.items():
                if col not in have:                          # database creato da una versione precedente
                    c.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")

    def _c(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.path), timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return _Ctx(con)

    # ---- utenti ------------------------------------------------------------
    def create_user(self, username: str, password: str, role: str = ROLE_USER) -> Dict[str, Any]:
        username, password = validate_username(username), validate_password(password)
        if role not in ROLES:
            raise AppError("Invalid role.")
        salt, h = hash_password(password)
        try:
            with self._c() as c:
                uid = c.execute("INSERT INTO users(username,role,salt,pw_hash,created) VALUES(?,?,?,?,?)",
                                (username, role, salt, h, time.time())).lastrowid
        except sqlite3.IntegrityError:
            raise AppError("Username already taken.", 409)
        return self.get_user(uid)

    def get_user(self, uid: int) -> Optional[Dict[str, Any]]:
        with self._c() as c:
            r = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return _public(r) if r else None

    def list_users(self) -> List[Dict[str, Any]]:
        with self._c() as c:
            return [_public(r) for r in c.execute("SELECT * FROM users ORDER BY username COLLATE NOCASE")]

    def count_admins(self) -> int:
        with self._c() as c:
            return c.execute("SELECT COUNT(*) FROM users WHERE role=? AND active=1", (ROLE_SERVER,)).fetchone()[0]

    def update_user(self, uid: int, role: Optional[str] = None, active: Optional[bool] = None,
                    password: Optional[str] = None, quota_mb: Optional[int] = None) -> Dict[str, Any]:
        u = self.get_user(uid)
        if not u:
            raise AppError("User not found.", 404)
        demoting = u["role"] == ROLE_SERVER and u["active"] and (
            (role is not None and role != ROLE_SERVER) or (active is not None and not active))
        if demoting and self.count_admins() <= 1:
            raise AppError("At least one active administrator must remain.")
        with self._c() as c:
            if role is not None:
                if role not in ROLES:
                    raise AppError("Invalid role.")
                c.execute("UPDATE users SET role=? WHERE id=?", (role, uid))
            if active is not None:
                c.execute("UPDATE users SET active=? WHERE id=?", (1 if active else 0, uid))
                if not active:
                    c.execute("DELETE FROM tokens WHERE user_id=?", (uid,))
            if quota_mb is not None:
                if not isinstance(quota_mb, int) or isinstance(quota_mb, bool) or not 0 <= quota_mb <= 1 << 20:
                    raise AppError("Invalid quota.")
                c.execute("UPDATE users SET quota_mb=? WHERE id=?", (quota_mb, uid))
            if password is not None:
                salt, h = hash_password(validate_password(password))
                c.execute("UPDATE users SET salt=?,pw_hash=?,failed=0,locked_until=0 WHERE id=?", (salt, h, uid))
                c.execute("DELETE FROM tokens WHERE user_id=?", (uid,))
        return self.get_user(uid)

    def promote(self, uid: int) -> Dict[str, Any]:
        """Rende l'account amministratore in modo permanente (chiave di accesso corretta)."""
        return self.update_user(uid, role=ROLE_SERVER)

    def update_profile(self, uid: int, data: Dict[str, Any]) -> Dict[str, Any]:
        values: Dict[str, str] = {}
        for field, limit in PROFILE_FIELDS.items():
            if field not in data:
                continue
            v = data[field]
            if not isinstance(v, str):
                raise AppError("Invalid value for {field}.", field=field)
            v = v.strip()
            if len(v) > limit:
                raise AppError("{field} is too long (max {n} characters).", field=field, n=limit)
            if field == "email" and v and not _EMAIL.match(v):
                raise AppError("Invalid email address.")
            values[field] = v
        if values:
            with self._c() as c:
                c.execute("UPDATE users SET " + ",".join(f"{k}=?" for k in values) + " WHERE id=?",
                          (*values.values(), uid))
        return self.get_user(uid)

    def delete_user(self, uid: int) -> None:
        u = self.get_user(uid)
        if not u:
            raise AppError("User not found.", 404)
        if u["role"] == ROLE_SERVER and u["active"] and self.count_admins() <= 1:
            raise AppError("At least one active administrator must remain.")
        with self._c() as c:
            c.execute("DELETE FROM users WHERE id=?", (uid,))

    # ---- accesso -----------------------------------------------------------
    def authenticate(self, username: str, password: str) -> Dict[str, Any]:
        """Verifica le credenziali (5 password errate -> account bloccato 5 minuti). Non emette token."""
        with self._c() as c:
            r = c.execute("SELECT * FROM users WHERE username=?", ((username or "").strip(),)).fetchone()
            if r is None:
                hash_password(password or "")          # tempo di risposta simile se l'utente non esiste
                raise AppError("Invalid credentials.", 401)
            now = time.time()
            if r["locked_until"] > now:
                left = r["locked_until"] - now
                raise AppError("Too many attempts: try again in {minutes} min.", 429,
                               minutes=max(1, int((left + 59) // 60)), scope="account", retry_after=int(left) + 1)
            if not r["active"]:
                raise AppError("Account disabled.", 403)
            if not verify_password(password or "", r["salt"], r["pw_hash"]):
                fails = r["failed"] + 1
                lock = now + LOGIN_LOCK_SECONDS if fails >= LOGIN_MAX_FAILS else 0
                c.execute("UPDATE users SET failed=?, locked_until=? WHERE id=?", (0 if lock else fails, lock, r["id"]))
                c.commit()
                raise AppError("Invalid credentials.", 401)
            c.execute("UPDATE users SET failed=0, locked_until=0, last_login=? WHERE id=?", (now, r["id"]))
        return self.get_user(r["id"])

    def issue_token(self, uid: int) -> str:
        token, now = new_token(), time.time()
        with self._c() as c:
            c.execute("DELETE FROM tokens WHERE expires<?", (now,))
            c.execute("INSERT INTO tokens(digest,user_id,expires) VALUES(?,?,?)",
                      (token_digest(token), uid, now + TOKEN_TTL))
        return token

    def user_from_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        with self._c() as c:
            r = c.execute("""SELECT u.* FROM tokens t JOIN users u ON u.id=t.user_id
                             WHERE t.digest=? AND t.expires>? AND u.active=1""",
                          (token_digest(token), time.time())).fetchone()
        return _public(r) if r else None

    def logout(self, token: str) -> None:
        with self._c() as c:
            c.execute("DELETE FROM tokens WHERE digest=?", (token_digest(token),))

    # ---- registro attivita' ------------------------------------------------
    def log(self, username: str, action: str, area: str = "", path: str = "", size: int = 0) -> None:
        with self._c() as c:
            c.execute("INSERT INTO events(ts,username,action,area,path,size) VALUES(?,?,?,?,?,?)",
                      (time.time(), username, action, area, path, size))

    def events(self, limit: int = 200) -> List[Dict[str, Any]]:
        with self._c() as c:
            return [dict(r) for r in c.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))]


class _Ctx:
    """Connessione che fa commit all'uscita e si chiude sempre."""
    def __init__(self, con):
        self.con = con

    def __enter__(self):
        return self.con

    def __exit__(self, et, ev, tb):
        try:
            if et is None:
                self.con.commit()
        finally:
            self.con.close()
        return False


def _public(r: sqlite3.Row) -> Dict[str, Any]:
    out = {"id": r["id"], "username": r["username"], "role": r["role"], "active": bool(r["active"]),
           "created": r["created"], "last_login": r["last_login"],
           "quota_mb": r["quota_mb"] or DEFAULT_QUOTA_MB}
    out.update({f: r[f] for f in PROFILE_FIELDS})
    return out
