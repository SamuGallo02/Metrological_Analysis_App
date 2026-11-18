"""Queue of the jobs requested from the browser: analyses and enhancements (params["type"]). Standard library only: the computation itself is done by an
`engine` (see engine.py), so the queue can be tested without OpenCV/YOLO.

One worker thread runs the jobs one after the other (a single GPU is shared by every user). Each job keeps its
results in <data>/web_jobs/<id>/: results.json and one overlay image per stereo pair.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import queue
import secrets
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.errors import AppError

from .params import JOB_KEEP_SECONDS, JOBS_PER_USER

log = logging.getLogger("webapp.jobs")

QUEUED, RUNNING, DONE, FAILED, CANCELLED = "queued", "running", "done", "error", "cancelled"
ACTIVE = (QUEUED, RUNNING)


@dataclass
class Job:
    id: str
    owner: str
    params: Dict[str, Any]
    folder: Path                                      # where its results are saved
    status: str = QUEUED
    done: int = 0
    total: int = 0
    error: str = ""
    created: float = field(default_factory=time.time)
    finished: float = 0.0
    tracked: int = 0                                  # distinct subjects followed across the pairs
    progress: float = 0.0                             # 0-1 inside the current item (a long video)
    results: List[Dict[str, Any]] = field(default_factory=list)
    stop: threading.Event = field(default_factory=threading.Event)

    @property
    def type(self) -> str:
        return self.params.get("type", "analysis")

    def summary(self) -> Dict[str, Any]:
        """The parameters of the job (never the private ones, "_...": server paths) and its state."""
        out = {k: v for k, v in self.params.items() if not k.startswith("_")}
        out.update({"id": self.id, "type": self.type, "owner": self.owner, "status": self.status, "done": self.done,
                    "total": self.total, "progress": round(self.progress, 3), "error": self.error,
                    "created": int(self.created), "finished": int(self.finished), "tracked": self.tracked})
        return out

    def full(self) -> Dict[str, Any]:
        out = self.summary()
        out["results"] = self.results
        return out


class JobManager:
    """engine.run(params, emit, should_stop, set_total) does the work: emit(result_dict, overlay_jpeg, tracked)
    is called once per stereo pair."""

    def __init__(self, root: Path, engine: Any, keep_seconds: int = JOB_KEEP_SECONDS, per_user: int = JOBS_PER_USER):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.engine = engine
        self.keep_seconds, self.per_user = keep_seconds, per_user
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._queue: "queue.Queue[Optional[str]]" = queue.Queue()
        self._clean_leftovers()
        self._thread = threading.Thread(target=self._work, name="analysis-worker", daemon=True)
        self._thread.start()

    # ---- requests ---------------------------------------------------------
    def submit(self, owner: str, params: Dict[str, Any]) -> Dict[str, Any]:
        kind = params.get("type", "analysis")
        with self._lock:
            if any(j.owner == owner and j.status in ACTIVE and j.type == kind for j in self._jobs.values()):
                if kind == "analysis":
                    raise AppError("You already have an analysis running: wait for it to finish or cancel it.", 409)
                raise AppError("You already have an enhancement running: wait for it to finish or cancel it.", 409)
            job_id = secrets.token_hex(8)
            job = Job(job_id, owner, dict(params), self.root / job_id)
            job.folder.mkdir(parents=True)
            self._jobs[job_id] = job
            self._prune_locked(owner)
        self._queue.put(job_id)
        log.info("analysis %s queued by %s", job_id, owner)
        return job.summary()

    def get(self, job_id: str, user: str, admin: bool = False, groups=()) -> Job:
        """groups: the work groups of the user, whose shared analyses they may read (only the owner changes a job)."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None or not (job.owner == user or admin or (job.params.get("group") or None) in groups):
            raise AppError("Resource not found.", 404)
        return job

    def list(self, user: str, groups=(), kind: Optional[str] = None) -> List[Dict[str, Any]]:
        """The user's jobs and those shared with their work groups (of one type, if given)."""
        with self._lock:
            jobs = [j for j in self._jobs.values() if (j.owner == user or (j.params.get("group") or None) in groups)
                    and (kind is None or j.type == kind)]
        return [j.summary() for j in sorted(jobs, key=lambda j: j.created, reverse=True)]

    def queue_position(self, job: Job) -> int:
        """How many jobs run before this one (0 = it is running or next)."""
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status in ACTIVE and j.created < job.created)

    def cancel(self, job_id: str, user: str, admin: bool = False) -> Dict[str, Any]:
        job = self.get(job_id, user, admin)
        if job.status in ACTIVE:
            job.stop.set()
            if job.status == QUEUED:
                self._finish(job, CANCELLED)
        return job.summary()

    def delete(self, job_id: str, user: str, admin: bool = False) -> None:
        job = self.get(job_id, user, admin)
        job.stop.set()
        with self._lock:
            self._jobs.pop(job.id, None)
        if job.status != RUNNING:
            shutil.rmtree(job.folder, ignore_errors=True)
        # a running job removes its own folder when it notices it was deleted (see _work)

    def overlay(self, job: Job, index: int) -> Path:
        p = job.folder / f"overlay_{index:05d}.jpg"
        if not (0 <= index < len(job.results)) or not p.is_file():
            raise AppError("Resource not found.", 404)
        return p

    def shutdown(self) -> None:
        for j in list(self._jobs.values()):
            j.stop.set()
        self._queue.put(None)

    # ---- worker -----------------------------------------------------------
    def _work(self) -> None:
        while True:
            job_id = self._queue.get()
            if job_id is None:
                return
            with self._lock:
                job = self._jobs.get(job_id)
            if job is None or job.status != QUEUED:
                continue
            job.status = RUNNING
            try:
                extra = {} if job.type == "analysis" else {"progress": lambda f, j=job: setattr(j, "progress", f)}
                self.engine.run(job.params, lambda r, img, n, j=job: self._emit(j, r, img, n),
                                job.stop.is_set, lambda n, j=job: setattr(j, "total", n), **extra)
                self._finish(job, CANCELLED if job.stop.is_set() else DONE)
            except AppError as e:
                job.error = str(e)
                self._finish(job, FAILED)
            except Exception as e:                       # the engine's libraries can fail in many ways
                log.exception("analysis %s failed", job.id)
                job.error = str(e) or e.__class__.__name__
                self._finish(job, FAILED)
            with self._lock:
                deleted = job.id not in self._jobs
            if deleted:
                shutil.rmtree(job.folder, ignore_errors=True)

    def _emit(self, job: Job, result: Dict[str, Any], overlay_jpeg: Optional[bytes], tracked: int) -> None:
        index = len(job.results)
        if overlay_jpeg:
            (job.folder / f"overlay_{index:05d}.jpg").write_bytes(overlay_jpeg)
        result = dict(result, index=index, overlay=bool(overlay_jpeg))
        job.results.append(result)
        job.done, job.tracked, job.progress = index + 1, tracked, 0.0

    def _finish(self, job: Job, status: str) -> None:
        job.status, job.finished = status, time.time()
        try:
            (job.folder / "results.json").write_text(json.dumps(job.full()), encoding="utf-8")
        except OSError:
            pass
        log.info("analysis %s: %s (%d/%d pairs)", job.id, status, job.done, job.total)

    # ---- housekeeping -----------------------------------------------------
    def _prune_locked(self, owner: str) -> None:
        """Drops the finished jobs that are too old, and the oldest of a user beyond `per_user`. Call with _lock."""
        now = time.time()
        finished = sorted((j for j in self._jobs.values() if j.status not in ACTIVE), key=lambda j: j.created)
        mine = [j for j in finished if j.owner == owner]
        drop = {j.id for j in finished if now - j.finished > self.keep_seconds}
        drop |= {j.id for j in mine[:max(0, len(mine) - self.per_user)]}
        for jid in drop:
            job = self._jobs.pop(jid)
            shutil.rmtree(job.folder, ignore_errors=True)

    def _clean_leftovers(self) -> None:
        """Jobs live in memory: the folders left by a previous run of the server are deleted."""
        for p in self.root.iterdir():
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)


# ---- report ---------------------------------------------------------------------
DETAIL_COLUMNS = ("timestamp", "track_id", "label", "confidence", "length_mm", "width_mm", "depth_mm",
                  "contact_distance_mm")


def _num(v: Any, digits: int = 2) -> str:
    return "" if v is None else f"{v:.{digits}f}"


def report_csv(job: Job) -> str:
    """The same two sections as the desktop export (reporting.export_csv): mean per subject, then every detection."""
    rows = [(r["timestamp"], d) for r in job.results for d in r.get("detections", [])]
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for _ts, d in rows:
        groups.setdefault((d.get("track_id") or "N/D", d["label"]), []).append(d)

    def mean(ds: List[Dict[str, Any]], key: str) -> Optional[float]:
        vals = [d[key] for d in ds if d.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    out.write("=== STATISTICHE AGGREGATE PER ID ===\n")
    w.writerow(["ID", "Classe", "Apparizioni", "Lunghezza Media (mm)", "Larghezza Media (mm)", "Confidenza Media"])
    for (tid, label), ds in sorted(groups.items()):
        w.writerow([tid, label, len(ds), _num(mean(ds, "length_mm")), _num(mean(ds, "width_mm")),
                    _num(mean(ds, "confidence"), 3)])
    out.write("\n=== DETTAGLIO RILEVAMENTI PER FOTOGRAMMA ===\n")
    w.writerow(DETAIL_COLUMNS)
    for ts, d in rows:
        w.writerow([ts, d.get("track_id") or "N/D", d["label"], _num(d["confidence"], 4), _num(d.get("length_mm")),
                    _num(d.get("width_mm")), _num(d.get("depth_mm")), _num(d.get("contact_distance_mm"))])
    return out.getvalue()

