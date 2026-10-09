"""HTTP (JSON) API of the server. Standard library only.

Authentication: header  Authorization: Bearer <token>  (obtained with /api/login).
Errors have the form {"error": English text, "key": ..., "params": {...}, "retry_after": s}: the client
translates them into the user's language.
"""
from __future__ import annotations

import json
import logging
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from common.errors import AppError
from common.params import AREA_MINE, ROLE_SERVER, ROLE_USER

from .config import ServerConfig, key_matches, load_admin_key
from .db import Database
from .params import API_VERSION, KEY_LOCK_SECONDS, KEY_MAX_FAILS, MAX_JSON
from .storage import Storage
from .throttle import Throttle

log = logging.getLogger("server")
CHUNK = 1 << 20


class Handler(BaseHTTPRequestHandler):
    server_version = "AnalisiServer/2"
    protocol_version = "HTTP/1.1"
    db: Database
    store: Storage
    cfg: ServerConfig
    key_throttle: Throttle

    # ---- utilities ----------------------------------------------------------
    def log_message(self, fmt, *args):
        log.info("%s %s", self.address_string(), fmt % args)

    def _ip(self) -> str:
        return self.cfg.client_ip(self.client_address[0], self.headers.get("X-Forwarded-For"))

    def _send(self, status: int, payload: Any = None, headers: Optional[Dict[str, str]] = None) -> None:
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _fail(self, e: AppError) -> None:
        self._send(e.status, e.payload(), {"Retry-After": str(e.retry_after)} if e.retry_after else None)

    def _json(self) -> Dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_JSON:
            raise AppError("Request too large.", 413)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            raise AppError("Invalid JSON.")
        if not isinstance(data, dict):
            raise AppError("Invalid JSON.")
        return data

    def _user(self) -> Optional[Dict[str, Any]]:
        h = self.headers.get("Authorization", "")
        return self.db.user_from_token(h[7:].strip()) if h.lower().startswith("bearer ") else None

    def _drain(self) -> None:
        """Discards the unread body (the connection is keep-alive)."""
        n = int(self.headers.get("Content-Length") or 0)
        while n > 0:
            chunk = self.rfile.read(min(n, CHUNK))
            if not chunk:
                break
            n -= len(chunk)

    # ---- administrator access key -----------------------------------
    def _use_key(self, key: Any, *extra_ids: str) -> bool:
        """True if the key is correct; False if it was not provided; AppError if wrong or blocked.
        5 errors from the same address (or on the same account) block ONLY the key for 5 minutes."""
        key = str(key or "")
        if not key:
            return False
        ids = ("ip:" + self._ip(),) + tuple(extra_ids)
        self.key_throttle.check(*ids)
        if key_matches(key, self.cfg.admin_key):
            self.key_throttle.reset(*ids)
            return True
        self.key_throttle.fail(*ids)
        if not self.cfg.admin_key:
            raise AppError("The access key is not enabled on this server.", 403)
        raise AppError("Invalid access key.", 403)

    # ---- dispatching -------------------------------------------------------
    def do_GET(self): self._route()
    def do_POST(self): self._route()
    def do_PUT(self): self._route()
    def do_PATCH(self): self._route()
    def do_DELETE(self): self._route()
    def do_HEAD(self): self._route()

    def _route(self) -> None:
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        path, method = url.path.rstrip("/"), self.command
        try:
            if path == "/api/health" and method in ("GET", "HEAD"):
                return self._send(200, {"ok": True, "api": API_VERSION, "register": self.cfg.allow_register,
                                        "key": bool(self.cfg.admin_key)})
            if path == "/api/login" and method == "POST":
                return self._login(self._json())
            if path == "/api/register" and method == "POST":
                return self._register(self._json())

            user = self._user()
            if user is None:
                self._drain()
                raise AppError("Sign-in required.", 401)
            admin = user["role"] == ROLE_SERVER

            if path in ("/api/me", "/api/profile") and method == "GET":
                return self._send(200, {"user": user})
            if path == "/api/profile" and method == "PATCH":
                u = self.db.update_profile(user["id"], self._json())
                self.db.log(user["username"], "profile.update")
                return self._send(200, {"user": u})
            if path == "/api/usage" and method == "GET":
                return self._send(200, {"used": self.store.usage(user["username"]),
                                        "quota": user["quota_mb"] * (1 << 20)})
            if path == "/api/logout" and method == "POST":
                self._drain()
                self.db.logout(self.headers["Authorization"][7:].strip())
                return self._send(200, {"ok": True})
            if path == "/api/password" and method == "POST":
                d = self._json()
                self.db.authenticate(user["username"], str(d.get("old", "")))      # check the old password
                self.db.update_user(user["id"], password=str(d.get("new", "")))
                return self._send(200, {"ok": True})
            if path.startswith("/api/files"):
                return self._files(path, method, q, user, admin)
            if path.startswith("/api/users") or path == "/api/events":
                if not admin:
                    self._drain()
                    raise AppError("Reserved to administrators.", 403)
                return self._admin(path, method, q, user)
            self._drain()
            raise AppError("Resource not found.", 404)
        except AppError as e:
            self._fail(e)
        except (ConnectionError, BrokenPipeError):
            self.close_connection = True
        except Exception:
            log.exception("internal error")
            self.close_connection = True
            try:
                self._fail(AppError("Internal server error.", 500))
            except Exception:
                pass

    # ---- login -----------------------------------------------------------
    def _login(self, d: Dict[str, Any]) -> None:
        name = str(d.get("username", ""))
        user = self.db.authenticate(name, str(d.get("password", "")))
        # the key is checked only when the password is correct, so it reveals nothing to someone without the account
        promoted = self._use_key(d.get("key"), "user:" + user["username"].lower())
        if promoted and user["role"] != ROLE_SERVER:
            user = self.db.promote(user["id"])              # permanent administrator
            self.db.log(user["username"], "promote.admin_key")
        token = self.db.issue_token(user["id"])
        self.db.log(user["username"], "login")
        self._send(200, {"token": token, "user": user})

    def _register(self, d: Dict[str, Any]) -> None:
        if not self.cfg.allow_register:
            raise AppError("Registration is disabled: ask an administrator for an account.", 403)
        as_admin = self._use_key(d.get("key"))
        u = self.db.create_user(str(d.get("username", "")), str(d.get("password", "")),
                                ROLE_SERVER if as_admin else ROLE_USER, email=d.get("email") or "")
        self.db.log(u["username"], "register.admin" if as_admin else "register")
        self._send(201, {"user": u})

    # ---- administration ---------------------------------------------------
    def _admin(self, path: str, method: str, q: Dict[str, str], me: Dict[str, Any]) -> None:
        if path == "/api/events" and method == "GET":
            return self._send(200, {"events": self.db.events(int(q.get("limit", 200)))})
        if path == "/api/users" and method == "GET":
            return self._send(200, {"users": self.db.list_users()})
        if path == "/api/users" and method == "POST":
            d = self._json()
            u = self.db.create_user(str(d.get("username", "")), str(d.get("password", "")), str(d.get("role", ROLE_USER)))
            self.db.log(me["username"], "user.create", path=u["username"])
            return self._send(201, {"user": u})
        m = re.fullmatch(r"/api/users/(\d+)", path)
        if m:
            uid = int(m.group(1))
            if method == "PATCH":
                d = self._json()
                u = self.db.update_user(uid, role=d.get("role"), active=d.get("active"),
                                        password=d.get("password"), quota_mb=d.get("quota_mb"))
                self.db.log(me["username"], "user.update", path=u["username"])
                return self._send(200, {"user": u})
            if method == "DELETE":
                self._drain()
                if uid == me["id"]:
                    raise AppError("You cannot delete your own account.")
                target = self.db.get_user(uid)
                self.db.delete_user(uid)
                self.db.log(me["username"], "user.delete", path=(target or {}).get("username", ""))
                return self._send(200, {"ok": True})
        self._drain()
        raise AppError("Resource not found.", 404)

    # ---- files --------------------------------------------------------------
    def _files(self, path: str, method: str, q: Dict[str, str], user: Dict[str, Any], admin: bool) -> None:
        area, rel, name = q.get("area", ""), q.get("path", ""), user["username"]
        mine = area == AREA_MINE
        if path == "/api/files" and method == "GET":
            return self._send(200, self.store.list_dir(area, rel, admin, name))
        if path == "/api/files/download" and method in ("GET", "HEAD"):
            return self._download(area, rel, admin, name)
        if path == "/api/files/upload" and method in ("PUT", "POST"):
            return self._upload(area, rel, user, admin)
        if path == "/api/files/mkdir" and method == "POST":
            self._drain()
            made = self.store.mkdir(area, rel, admin, name)
            self.db.log(name, "mkdir", area, made)
            return self._send(201, {"path": made})
        if (method, path) in (("DELETE", "/api/files"), ("POST", "/api/files/move"), ("POST", "/api/files/approve")):
            if not (admin or (mine and path != "/api/files/approve")):       # in common areas only the admin
                self._drain()
                raise AppError("Users cannot modify or delete the server's shared files.", 403)
            if method == "DELETE":
                self._drain()
                self.store.delete(area, rel, name)
                self.db.log(name, "delete", area, rel)
                return self._send(200, {"ok": True})
            d = self._json()
            if path == "/api/files/move":
                dst = self.store.move(area, rel, str(d.get("to", "")), name)
                self.db.log(name, "move", area, f"{rel} -> {dst}")
                return self._send(200, {"path": dst})
            dst = self.store.approve_model(rel, d.get("name"))
            self.db.log(name, "approve", "models", dst)
            return self._send(200, {"path": dst})
        self._drain()
        raise AppError("Resource not found.", 404)

    def _download(self, area: str, rel: str, admin: bool, owner: str) -> None:
        path, size = self.store.open_file(area, rel, admin, owner)
        start, end, status = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng:
            m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
            if not m or (not m.group(1) and not m.group(2)):
                raise AppError("Invalid range.", 416)
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("X-File-Size", str(size))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                buf = f.read(min(CHUNK, left))
                if not buf:
                    break
                self.wfile.write(buf)
                left -= len(buf)

    def _upload(self, area: str, rel: str, user: Dict[str, Any], admin: bool) -> None:
        size = int(self.headers.get("Content-Length") or 0)
        owner = user["username"]
        try:
            dest, eff = self.store.check_new_file(area, rel, admin, owner, size, user["quota_mb"])
            if dest.exists() and not (admin or area == AREA_MINE):
                raise AppError("A file with this name already exists (you cannot overwrite it).", 409)
        except AppError:
            self.close_connection = True      # the body is not read: the connection is closed
            raise
        tmp = self.store.tmp_path(area, owner)
        got = 0
        try:
            with open(tmp, "wb") as f:
                while got < size:
                    buf = self.rfile.read(min(CHUNK, size - got))
                    if not buf:
                        raise ConnectionError("upload interrupted")
                    f.write(buf)
                    got += len(buf)
            self.store.commit_upload(tmp, dest, area, admin)
        finally:
            if tmp.exists():
                tmp.unlink()
        self.db.log(owner, "upload", area, eff, size)
        self._send(201, {"path": eff, "pending": area == "models" and eff.startswith("_pending/")})


class _Server(ThreadingHTTPServer):
    def handle_error(self, request, client_address):      # connection reset = client closing: not an error
        import sys
        if isinstance(sys.exc_info()[1], (ConnectionError, BrokenPipeError, TimeoutError)):
            return
        log.exception("error on connection %s", client_address)


def make_server(data_dir: Path, host: str = "127.0.0.1", port: int = 8765, allow_register: bool = True,
                admin_key: Optional[str] = None, trust_proxy: bool = False) -> ThreadingHTTPServer:
    """admin_key=None: the key is read from environment/file (see server.config); '' disables it."""
    data_dir = Path(data_dir)
    cfg = ServerConfig(data_dir, allow_register, load_admin_key(data_dir) if admin_key is None else admin_key,
                       trust_proxy)
    # one subclass per server: several servers in the same process (tests) do not share state
    handler = type("BoundHandler", (Handler,), {
        "key_throttle": Throttle(KEY_MAX_FAILS, KEY_LOCK_SECONDS), "db": Database(data_dir / "server.db"),
        "store": Storage(data_dir), "cfg": cfg})
    httpd = _Server((host, port), handler)
    httpd.handler = handler
    httpd.daemon_threads = True
    return httpd
