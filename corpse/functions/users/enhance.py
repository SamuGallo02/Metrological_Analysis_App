"""Asking the server to improve a photo or a video, and what to do with the answer.

The server has neither the algorithm nor the libraries: it keeps the queue and the files, a worker does the work
(`training_worker.py`). The steps are always the same:

    send(client, media)      the file goes into your personal folder on the server and a job is queued
    state(client, job)       how it is going (queued, running, done, failed)
    collect(client, job)     the improved file comes back to this computer
    keep(media, improved)    it is added beside the original, or takes its place

Qt-free: the interface only shows what happens here.

Autore: Samuele Gallo
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional

from common.image_enhance import enhanced_path
from common.label_store import read_labels, write_labels
from common.params import ENHANCE_INBOX, JOB_DONE, JOB_FAILED, JOB_OPEN, ORIGINALS_DIR

ADD, REPLACE = "add", "replace"


def remote_path(media: Path, stamp: Optional[float] = None) -> str:
    """Where the file waits on the server: the name is kept, with a moment in front so two files of the same
    name coming from different folders never meet."""
    when = time.strftime("%Y%m%d-%H%M%S", time.localtime(stamp if stamp is not None else time.time()))
    return f"{ENHANCE_INBOX}/{when}_{Path(media).name}"


def send(client: Any, media: Path, method: str = "") -> Dict[str, Any]:
    """Uploads the file and asks for the improvement. Returns the job."""
    media = Path(media)
    rel = remote_path(media)
    client.upload("mine", rel, media)
    return client.request_enhance(rel, method)


def state(client: Any, job: Dict[str, Any]) -> Dict[str, Any]:
    """The job as the server sees it now (the same one if the server cannot be asked)."""
    for current in client.enhance_jobs():
        if current["id"] == job["id"]:
            return current
    return job


def waiting(job: Dict[str, Any]) -> bool:
    return job.get("status") in JOB_OPEN


def failed(job: Dict[str, Any]) -> bool:
    return job.get("status") == JOB_FAILED


def done(job: Dict[str, Any]) -> bool:
    return job.get("status") == JOB_DONE and bool(job.get("result"))


def collect(client: Any, job: Dict[str, Any], folder: Path) -> Path:
    """Brings the improved file back to this computer, into `folder`."""
    if not done(job):
        raise ValueError("The improvement is not ready.")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / Path(job["result"]).name
    client.download(job["area"], job["result"], dest)
    return dest


def keep(media: Path, improved: Path, how: str = ADD) -> Path:
    """What the user chose: `ADD` puts the improved copy in `enhanced/` beside the original, `REPLACE` puts it in
    its place (the original is kept in `originals/`, so nothing is lost). Returns the file the user will see."""
    media, improved = Path(media), Path(improved)
    if how == REPLACE:
        safe = media.parent / ORIGINALS_DIR / media.name
        safe.parent.mkdir(parents=True, exist_ok=True)
        if not safe.exists():
            shutil.copy2(media, safe)
        shutil.copy2(improved, media)                      # same name: the labels still belong to this file
        return media
    dest = enhanced_path(media)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(improved, dest)
    text, classes, beside = read_labels(media)
    if text.strip():                                       # the copy keeps the labels of the original
        write_labels(dest, text, classes, beside)
    return dest


def cleanup(client: Any, job: Dict[str, Any]) -> None:
    """Removes from the server the file that was sent to be improved and the copy it produced."""
    for rel in (job.get("path", ""), job.get("result", "")):
        if not rel:
            continue
        try:
            client.delete(job.get("area", "mine"), rel)
        except Exception:                                  # noqa: BLE001 - already gone, or no right to remove it
            pass
