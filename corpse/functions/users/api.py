"""HTTP client for the server (standard library only)."""
from __future__ import annotations

import http.client
import json
import os
import socket
import ssl
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode, urlparse

from common.errors import AppError
from common.params import CHUNK, NET_TIMEOUT

Progress = Optional[Callable[[int, int], None]]     # (bytes_done, bytes_total)
Cancel = Optional[Callable[[], bool]]


class ApiError(AppError):
    """Server or network error; `key`/`params` are used to translate it (common.i18n.tr_error)."""


class OfflineError(ApiError):
    """Server unreachable (no network, wrong address, server down)."""


class Cancelled(ApiError):
    pass


def _from_payload(payload: Dict[str, Any], status: int) -> ApiError:
    params = dict(payload.get("params") or {})
    if payload.get("retry_after"):
        params["retry_after"] = payload["retry_after"]
    key = payload.get("key")
    if not key:                                       # response not produced by our server (proxy, etc.)
        key, params = "{msg}", {"msg": payload.get("error") or f"HTTP {status}"}
    return ApiError(key, status, **params)


def normalize_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        raise ApiError("Server address missing.")
    if "://" not in url:
        url = "https://" + url
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ApiError("Invalid server address.")
    return url


def is_secure(url: str) -> bool:
    p = urlparse(url)
    return p.scheme == "https" or p.hostname in ("localhost", "127.0.0.1", "::1")


class ApiClient:
    def __init__(self, base_url: str, token: Optional[str] = None, timeout: float = NET_TIMEOUT):
        self.base_url = normalize_url(base_url)
        self.token = token
        self.timeout = timeout
        self._p = urlparse(self.base_url)

    # ---- low level -----------------------------------------------------
    def _conn(self) -> http.client.HTTPConnection:
        if self._p.scheme == "https":
            return http.client.HTTPSConnection(self._p.hostname, self._p.port, timeout=self.timeout,
                                               context=ssl.create_default_context())
        return http.client.HTTPConnection(self._p.hostname, self._p.port, timeout=self.timeout)

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        h = {"Accept": "application/json"}
        if self.token:
            h["Authorization"] = "Bearer " + self.token
        h.update(extra or {})
        return h

    def _url(self, path: str, params: Optional[Dict[str, str]] = None) -> str:
        return self._p.path.rstrip("/") + path + ("?" + urlencode(params) if params else "")

    @staticmethod
    def _offline(e: Exception) -> OfflineError:
        return OfflineError("Server unreachable ({error}).", error=e.__class__.__name__)

    def _request(self, method: str, path: str, params: Optional[Dict[str, str]] = None,
                 body: Any = None) -> Dict[str, Any]:
        data, headers = None, self._headers()
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        conn = self._conn()
        try:
            conn.request(method, self._url(path, params), body=data, headers=headers)
            r = conn.getresponse()
            raw = r.read()
        except (OSError, http.client.HTTPException, socket.timeout) as e:
            raise self._offline(e) from e
        finally:
            conn.close()
        return self._parse(r.status, raw)

    @staticmethod
    def _parse(status: int, raw: bytes) -> Dict[str, Any]:
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            payload = {}
        if status >= 400:
            raise _from_payload(payload if isinstance(payload, dict) else {}, status)
        return payload

    # ---- accounts -----------------------------------------------------------
    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/api/health")

    def login(self, username: str, password: str, key: str = "") -> Dict[str, Any]:
        """key: access key (optional): if correct, the account becomes administrator permanently."""
        res = self._request("POST", "/api/login", body={"username": username, "password": password, "key": key})
        self.token = res["token"]
        return res["user"]

    def register(self, username: str, password: str, key: str = "", email: str = "") -> Dict[str, Any]:
        return self._request("POST", "/api/register",
                             body={"username": username, "password": password, "key": key, "email": email})["user"]

    def me(self) -> Dict[str, Any]:
        return self._request("GET", "/api/me")["user"]

    def logout(self) -> None:
        try:
            self._request("POST", "/api/logout")
        finally:
            self.token = None

    def change_password(self, old: str, new: str) -> None:
        self._request("POST", "/api/password", body={"old": old, "new": new})

    def update_profile(self, **fields: str) -> Dict[str, Any]:
        return self._request("PATCH", "/api/profile", body=fields)["user"]

    def usage(self) -> Dict[str, int]:
        return self._request("GET", "/api/usage")

    # ---- administration ---------------------------------------------------
    def users(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/api/users")["users"]

    def create_user(self, username: str, password: str, role: str) -> Dict[str, Any]:
        return self._request("POST", "/api/users", body={"username": username, "password": password,
                                                         "role": role})["user"]

    def update_user(self, uid: int, **fields: Any) -> Dict[str, Any]:
        return self._request("PATCH", f"/api/users/{uid}", body=fields)["user"]

    def delete_user(self, uid: int) -> None:
        self._request("DELETE", f"/api/users/{uid}")

    def events(self, limit: int = 200) -> List[Dict[str, Any]]:
        return self._request("GET", "/api/events", {"limit": str(limit)})["events"]

    # ---- files --------------------------------------------------------------
    def list(self, area: str, path: str = "") -> List[Dict[str, Any]]:
        return self._request("GET", "/api/files", {"area": area, "path": path})["entries"]

    def mkdir(self, area: str, path: str) -> str:
        return self._request("POST", "/api/files/mkdir", {"area": area, "path": path})["path"]

    def delete(self, area: str, path: str) -> None:
        self._request("DELETE", "/api/files", {"area": area, "path": path})

    def move(self, area: str, src: str, dst: str) -> str:
        return self._request("POST", "/api/files/move", {"area": area, "path": src}, {"to": dst})["path"]

    def approve(self, path: str, name: Optional[str] = None) -> str:
        return self._request("POST", "/api/files/approve", {"area": "models", "path": path}, {"name": name})["path"]

    def upload(self, area: str, remote_path: str, local: Path, progress: Progress = None,
               cancel: Cancel = None) -> Dict[str, Any]:
        local = Path(local)
        size = local.stat().st_size
        conn = self._conn()
        try:
            conn.putrequest("PUT", self._url("/api/files/upload", {"area": area, "path": remote_path}))
            for k, v in self._headers({"Content-Type": "application/octet-stream",
                                       "Content-Length": str(size)}).items():
                conn.putheader(k, v)
            conn.endheaders()
            sent = 0
            with open(local, "rb") as f:
                while True:
                    if cancel and cancel():
                        raise Cancelled("Cancelled.")
                    buf = f.read(CHUNK)
                    if not buf:
                        break
                    conn.send(buf)
                    sent += len(buf)
                    if progress:
                        progress(sent, size)
            r = conn.getresponse()
            raw = r.read()
        except (OSError, http.client.HTTPException, socket.timeout) as e:
            # the server may reject right away (e.g. 409) and close while we are still sending
            try:
                r = conn.getresponse()
                raw = r.read()
            except Exception:
                raise OfflineError("Connection interrupted during upload ({error}).",
                                   error=e.__class__.__name__) from e
        finally:
            conn.close()
        return self._parse(r.status, raw)

    def download(self, area: str, remote_path: str, dest: Path, progress: Progress = None,
                 cancel: Cancel = None) -> Path:
        """Downloads to dest; if dest.part exists, resumes from where it left off."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = Path(str(dest) + ".part")
        have = part.stat().st_size if part.exists() else 0
        conn = self._conn()
        try:
            headers = self._headers({"Range": f"bytes={have}-"} if have else None)
            conn.request("GET", self._url("/api/files/download", {"area": area, "path": remote_path}),
                         headers=headers)
            r = conn.getresponse()
            if r.status == 416 and have:           # part already complete
                r.read()
                os.replace(part, dest)
                return dest
            if r.status >= 400:
                self._parse(r.status, r.read())
            if r.status == 200:
                have = 0                            # the server ignored the Range header: start over
            total = int(r.getheader("X-File-Size") or (int(r.getheader("Content-Length") or 0) + have))
            with open(part, "ab" if have else "wb") as f:
                got = have
                while True:
                    if cancel and cancel():
                        raise Cancelled("Cancelled (the partial file is kept to resume).")
                    buf = r.read(CHUNK)
                    if not buf:
                        break
                    f.write(buf)
                    got += len(buf)
                    if progress:
                        progress(got, total)
            if total and got != total:
                raise OfflineError("Incomplete download: try again to resume it.")
        except (OSError, http.client.HTTPException, socket.timeout) as e:
            raise self._offline(e) from e
        finally:
            conn.close()
        os.replace(part, dest)
        return dest
