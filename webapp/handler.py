"""Request handler of the web application: the server's whole API (server.app.Handler), plus
  /                         the pages for the browser (webapp/static)
  /api/i18n?lang=it         the translations of the application (common/translations) for the pages
  /api/analysis/...         metrological analysis run on the server (queue in jobs.py, computation in engine.py)
  /api/enhance/...          underwater image enhancement (nautilus, in enhance.py): preview and background jobs
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict
from urllib.parse import parse_qs, unquote, urlparse

from common.errors import AppError
from common.params import AREA_GROUPS, AREA_MINE, KIND_AREA, KIND_MODEL, ROLE_SERVER
from server.access import Access
from server.app import Handler
from server.params import PENDING
from server.db import check_visibility

from .engine import AnalysisEngine
from .enhance import EnhanceEngine, Engines, media_kind, output_name
from .jobs import JobManager, report_csv
from .params import (CONTENT_TYPES, JOBS_DIR, LANGUAGES, MODEL_SUFFIXES, SECURITY_HEADERS, STATIC_DIR, STEREO_DEFAULT,
                     STEREO_LIMITS)

TRANSLATIONS_DIR = Path(__file__).resolve().parent.parent / "common" / "translations"
_I18N_CACHE: Dict[str, Dict[str, str]] = {}


def load_strings(lang: str) -> Dict[str, str]:
    """STRINGS of common/translations/<lang>.py read as data (never executed), plus the web pages' own strings."""
    if lang not in LANGUAGES:
        raise AppError("Resource not found.", 404)
    if lang not in _I18N_CACHE:
        strings: Dict[str, str] = {}
        pack = TRANSLATIONS_DIR / f"{lang}.py"
        if pack.is_file():
            for node in ast.parse(pack.read_text(encoding="utf-8")).body:
                if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "STRINGS" for t in node.targets):
                    strings.update(ast.literal_eval(node.value))
        web = STATIC_DIR / "i18n" / f"{lang}.json"
        if web.is_file():
            strings.update(json.loads(web.read_text(encoding="utf-8")))
        _I18N_CACHE[lang] = strings
    return _I18N_CACHE[lang]


class WebHandler(Handler):
    jobs: JobManager
    engine: AnalysisEngine
    enhancer: EnhanceEngine

    @classmethod
    def setup_server(cls, httpd, data_dir: Path) -> None:
        """Called by server.app.make_server: one job queue per server (analyses and enhancements share the GPU)."""
        handler = httpd.handler
        handler.engine = getattr(cls, "engine_factory", AnalysisEngine)()
        handler.enhancer = getattr(cls, "enhance_factory", EnhanceEngine)()
        handler.engine.enhancer = handler.enhancer
        handler.jobs = JobManager(Path(data_dir) / JOBS_DIR, Engines(handler.engine, handler.enhancer))

    # ---- dispatching -------------------------------------------------------
    def _route(self) -> None:
        path = urlparse(self.path).path
        if path.startswith(("/api/analysis", "/api/enhance")) or path.rstrip("/") == "/api/i18n":
            return self._guarded(path.rstrip("/"))
        if path.startswith("/api/"):
            return super()._route()
        return self._static(path)

    def _guarded(self, path: str) -> None:
        """Same rules as the base API: rate limit, sign-in, errors as JSON."""
        method = self.command
        q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        try:
            self.counter[0] += 1
            try:
                self.limiter.hit(self._ip())
            except AppError:
                self._drain()
                raise
            if path == "/api/i18n" and method == "GET":              # public: the login page is translated too
                return self._send(200, {"lang": q.get("lang", ""), "strings": load_strings(q.get("lang", ""))},
                                  {"Cache-Control": "max-age=3600"})
            user = self._user()
            if user is None:
                self._drain()
                raise AppError("Sign-in required.", 401)
            admin = user["role"] == ROLE_SERVER
            if path.startswith("/api/enhance"):
                return self._enhance(path, method, q, user, admin)
            return self._analysis(path, method, q, user, admin)
        except AppError as e:
            self._fail(e)
        except (ConnectionError, BrokenPipeError):
            self.close_connection = True
        except Exception:
            import logging
            logging.getLogger("webapp").exception("internal error")
            self.close_connection = True
            try:
                self._fail(AppError("Internal server error.", 500))
            except Exception:
                pass

    # ---- inputs ---------------------------------------------------------------
    def _readable(self, spec: Any, user: Dict[str, Any], admin: bool, acc: Access):
        """(path, area, rel) of something the user may read: library items visible to them, their folder, their work groups'."""
        if not isinstance(spec, dict):
            raise AppError("Choose a folder or a file.", 422)
        area, rel = str(spec.get("area", "")), str(spec.get("path", ""))
        if area == AREA_GROUPS and not acc.group_of(rel):       # an outsider is not even told that it exists
            raise AppError("Folder not found.", 404)
        path, rel = self.store.resolve(area, rel, admin, user["username"])
        acc.check_file(area, rel)
        if not path.exists():
            raise AppError("File not found.", 404)
        return path, area, rel

    def _resolve_input(self, spec: Any, user: Dict[str, Any], admin: bool, want_dir: bool, acc: Access) -> Path:
        if not isinstance(spec, dict):
            raise AppError("Choose a folder and a model.", 422)
        path, area, rel = self._readable(spec, user, admin, acc)
        if want_dir:
            if not path.is_dir():
                raise AppError("Folder not found.", 404)
            if acc.contains_hidden(area, rel):                  # the analysis must not read items hidden from the user
                raise AppError("Choose one item of the library, not the folder that holds it.", 422)
            return path
        if not path.is_file() or path.suffix.lower() not in MODEL_SUFFIXES:
            raise AppError("Choose a YOLO model (.pt or .onnx file).", 422)
        # A .pt is a pickle archive: loading it runs any code inside it. Only models an administrator approved into
        # the library are loaded as .pt; personal and group folders may hold .onnx models (no code inside).
        if path.suffix.lower() == ".pt" and (area != KIND_AREA[KIND_MODEL] or rel.split("/", 1)[0] == PENDING):
            raise AppError("A .pt model must come from the library (approved by an administrator); "
                           "from your folder use an .onnx model.", 422)
        return path

    def _shared_with(self, d: Dict[str, Any], acc: Access) -> Any:
        _vis, group = check_visibility(None, d.get("group"))                 # one work group, or nobody
        acc.check_group(group)
        return group

    # ---- analysis -----------------------------------------------------------
    def _analysis(self, path: str, method: str, q: Dict[str, str], user: Dict[str, Any], admin: bool) -> None:
        name = user["username"]
        acc = Access(self.db, user, admin)
        if path == "/api/analysis/status" and method == "GET":
            return self._send(200, dict(self.engine.status(), defaults=STEREO_DEFAULT))
        if path == "/api/analysis/classes" and method == "GET":
            model = self._resolve_input({"area": q.get("area"), "path": q.get("path")}, user, admin, False, acc)
            return self._send(200, {"classes": self.engine.classes(model)})
        if path == "/api/analysis/jobs" and method == "GET":
            return self._send(200, {"jobs": self._named(self.jobs.list(name, acc.groups, "analysis"))})
        if path == "/api/analysis/jobs" and method == "POST":
            d = self._json()
            status = self.engine.status()
            if not status["available"]:
                raise AppError("The analysis is not available on this server ({reason}).", 503, reason=status["reason"])
            folder = self._resolve_input(d.get("source"), user, admin, True, acc)
            model = self._resolve_input(d.get("model"), user, admin, False, acc)
            params: Dict[str, Any] = {"source": {"area": d["source"]["area"], "path": d["source"].get("path", "")},
                                      "model": {"area": d["model"]["area"], "path": d["model"]["path"]},
                                      "label": str(d.get("label") or "").strip()[:100] or None,
                                      "detect_right": bool(d.get("detect_right", True)),
                                      "_folder": str(folder), "_model_file": str(model),
                                      "group": self._shared_with(d, acc), "type": "analysis", "enhance": None}
            if isinstance(d.get("enhance"), dict) and d["enhance"].get("method"):
                params["enhance"] = self.enhancer.check_method(d["enhance"]["method"], d["enhance"].get("params"))
            for k, (lo, hi) in STEREO_LIMITS.items():
                try:
                    v = float(d.get(k, STEREO_DEFAULT[k]))
                except (TypeError, ValueError):
                    raise AppError("Invalid value for {field}.", 422, field=k)
                if not lo <= v <= hi:
                    raise AppError("Invalid value for {field}.", 422, field=k)
                params[k] = v
            job = self.jobs.submit(name, params)
            self.db.log(name, "analysis.start", d["source"]["area"], params["source"]["path"])
            return self._send(201, {"job": self._named([job])[0]})
        return self._job_routes("analysis", path, method, q, name, admin, acc)

    # ---- enhancement ---------------------------------------------------------
    def _output_for(self, src: Path, area: str, rel: str, method: str, user: Dict[str, Any], admin: bool):
        """Where the results go: next to the original (a sibling "<name>_<method>" folder, or "<stem>_<method>.<ext>"
        file) in the user's folder or group folder; the library is read-only, so its items go to the user's folder."""
        if area in (AREA_MINE, AREA_GROUPS):
            out_area, parent = area, PurePosixPath(rel).parent.as_posix()
            parent = "" if parent == "." else parent
            if area == AREA_GROUPS and "/" not in rel:
                raise AppError("Choose a folder or a file inside the folder of the group.", 422)
            if area == AREA_MINE and not rel:
                raise AppError("Choose a folder or a file inside your folder.", 422)
        else:
            out_area, parent = AREA_MINE, ""
        stem = src.stem if src.is_file() else src.name
        suffix = PurePosixPath(output_name(src)).suffix if src.is_file() else ""
        for n in range(1, 1000):
            candidate = f"{stem}_{method}" + (f"_{n}" if n > 1 else "") + suffix
            out_rel = f"{parent}/{candidate}" if parent else candidate
            out_path, out_rel = self.store.resolve(out_area, out_rel, admin, user["username"])
            if not out_path.exists():
                break
        else:
            raise AppError("Already exists.", 409)
        if out_area == AREA_GROUPS:
            group = Access(self.db, user, admin).group_of(out_rel)
            quota_root, quota = self.store.base(AREA_GROUPS, "") / group, self.db.group_quota(group)
        else:
            quota_root, quota = self.store.base(AREA_MINE, user["username"]), user["quota_mb"]
        return out_area, out_rel, out_path, quota_root, quota << 20

    def _enhance(self, path: str, method: str, q: Dict[str, str], user: Dict[str, Any], admin: bool) -> None:
        name = user["username"]
        acc = Access(self.db, user, admin)
        if path == "/api/enhance/status" and method == "GET":
            return self._send(200, self.enhancer.status())
        if path == "/api/enhance/preview" and method == "POST":
            d = self._json()
            src, _area, _rel = self._readable(d.get("source"), user, admin, acc)
            if not src.is_file():
                raise AppError("Choose a photo or a video.", 422)
            try:
                seconds = float(d.get("seconds") or 0)
            except (TypeError, ValueError):
                raise AppError("Invalid value for {field}.", 422, field="seconds")
            methods = d.get("methods") if isinstance(d.get("methods"), list) else []
            return self._send(200, self.enhancer.preview(src, methods, seconds))
        if path == "/api/enhance/jobs" and method == "GET":
            return self._send(200, {"jobs": self._named(self.jobs.list(name, acc.groups, "enhance"))})
        if path == "/api/enhance/jobs" and method == "POST":
            d = self._json()
            checked = self.enhancer.check_method(d.get("method"), d.get("params"))
            src, area, rel = self._readable(d.get("source"), user, admin, acc)
            if src.is_file() and media_kind(src) is None:
                raise AppError("Choose a photo or a video.", 422)
            out_area, out_rel, out_path, quota_root, quota = self._output_for(src, area, rel, checked["method"], user, admin)
            if src.is_dir():
                out_path.mkdir(parents=True)                        # reserves the name
            params = {"type": "enhance", "source": {"area": area, "path": rel}, "output": {"area": out_area, "path": out_rel},
                      "method": checked["method"], "params": checked["params"], "group": self._shared_with(d, acc),
                      "_source": str(src), "_output": str(out_path), "_quota_root": str(quota_root), "_quota_bytes": quota,
                      # library items hidden from the user inside the chosen folder: never read
                      "_exclude": [str(self.store.resolve(area, h, admin, name)[0]) for h in acc.hidden_under(area, rel)]
                      if src.is_dir() else []}
            try:
                job = self.jobs.submit(name, params)
            except AppError:
                if src.is_dir():
                    out_path.rmdir()
                raise
            self.db.log(name, "enhance.start", area, rel)
            return self._send(201, {"job": self._named([job])[0]})
        return self._job_routes("enhance", path, method, q, name, admin, acc)

    # ---- one job ----------------------------------------------------------------
    def _job_routes(self, kind: str, path: str, method: str, q: Dict[str, str], name: str, admin: bool,
                    acc: Access) -> None:
        m = re.fullmatch(rf"/api/{kind}/jobs/([0-9a-f]{{16}})(?:/(cancel|csv|overlay/(\d+)))?", path)
        if not m:
            self._drain()
            raise AppError("Resource not found.", 404)
        job = self.jobs.get(m.group(1), name, admin, acc.groups)
        if job.type != kind:
            raise AppError("Resource not found.", 404)
        action = m.group(2) or ""
        if not action and method == "GET":
            out = self._named([job.full()])[0]
            since = int(q.get("since", 0) or 0)                 # the page asks only for the results it does not have
            out["results"] = out["results"][since:]
            out["since"], out["queue"] = since, self.jobs.queue_position(job)
            return self._send(200, {"job": out})
        if not action and method == "DELETE":
            self._drain()
            self.jobs.delete(job.id, name, admin)
            return self._send(200, {"ok": True})
        if action == "cancel" and method == "POST":
            self._drain()
            return self._send(200, {"job": self.jobs.cancel(job.id, name, admin)})
        if kind == "analysis" and action == "csv" and method == "GET":
            stem = PurePosixPath(job.params["source"]["path"] or job.params["source"]["area"]).name or "analysis"
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", stem)
            return self._send_bytes(200, report_csv(job).encode("utf-8"), "text/csv; charset=utf-8",
                                    {"Content-Disposition": f'attachment; filename="{safe}_analysis.csv"'})
        if kind == "analysis" and action.startswith("overlay") and method == "GET":
            return self._send_bytes(200, self.jobs.overlay(job, int(m.group(3))).read_bytes(), "image/jpeg",
                                    {"Cache-Control": "private, max-age=86400"})
        self._drain()
        raise AppError("Resource not found.", 404)

    def _named(self, jobs):
        return [dict(j, group=j.get("group", "")) for j in jobs]

    # ---- responses ---------------------------------------------------------
    def _send_bytes(self, status: int, body: bytes, ctype: str, headers: Dict[str, str] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        headers = dict({"Cache-Control": "no-store"}, **(headers or {}))
        for k, v in dict(SECURITY_HEADERS, **headers).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _static(self, path: str) -> None:
        """The files of webapp/static. Every other address gets the page (the page itself shows its sections)."""
        self._drain()
        if self.command not in ("GET", "HEAD"):
            return self._fail(AppError("Resource not found.", 404))
        rel = unquote(path).lstrip("/") or "index.html"
        root = STATIC_DIR.resolve()
        target = (root / rel).resolve()
        if root not in target.parents or not target.is_file():
            if PurePosixPath(rel).suffix:                       # a missing file (script, image...): 404
                return self._fail(AppError("Resource not found.", 404))
            target = root / "index.html"
        ctype = CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
        cache = "no-cache" if target.suffix == ".html" else "max-age=300"
        self._send_bytes(200, target.read_bytes(), ctype, {"Cache-Control": cache})
