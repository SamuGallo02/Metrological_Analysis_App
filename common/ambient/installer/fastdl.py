"""
Fast, resumable wheel download: parallel connections (in segments, with
the HTTP Range header), resuming of already downloaded segments after an interruption and
SHA-256 verification. Standard library only.

Why: the PyTorch GPU download is several GB and the server often limits the
speed of EACH connection; with more connections the total speed grows, and an
error halfway (disk full, network down) does not force a restart from scratch.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

SEGMENT = 8 * 1024 * 1024
BIG = 16 * 1024 * 1024        # below this threshold the file is downloaded with a single connection
_UA = {"User-Agent": "AnalisiMetrologica-Installer"}


class DownloadError(Exception):
    pass


def _request(url: str, rng: Optional[Tuple[int, int]] = None, timeout: int = 60):
    h = dict(_UA)
    if rng is not None:
        h["Range"] = f"bytes={rng[0]}-{rng[1]}"
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout)


def probe(url: str) -> Tuple[int, bool]:
    """(size, does the server support Range?)"""
    with _request(url, (0, 0)) as r:
        if r.status == 206:
            cr = r.headers.get("Content-Range", "")          # "bytes 0-0/12345"
            if "/" in cr and cr.rsplit("/", 1)[1].isdigit():
                return int(cr.rsplit("/", 1)[1]), True
        size = int(r.headers.get("Content-Length") or 0)
    return size, False


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class _Counter:
    def __init__(self, cb: Optional[Callable[[int], None]]):
        self.lock = threading.Lock()
        self.cb = cb

    def add(self, n: int) -> None:
        if self.cb and n:
            with self.lock:
                self.cb(n)


def download_file(url: str, dest: Path, size: int, ranges: bool, sha256: Optional[str] = None,
                  workers: int = 6, on_bytes: Optional[Callable[[int], None]] = None,
                  cancel: Optional[Callable[[], bool]] = None) -> None:
    """Downloads url into dest. on_bytes(n) is called with the bytes just downloaded
    (including those already present from a previous attempt, counted at start)."""
    counter = _Counter(on_bytes)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and dest.stat().st_size == size and (not sha256 or sha256_of(dest) == sha256.lower()):
        counter.add(size)                       # already downloaded and intact
        return

    part = Path(str(dest) + ".part")
    meta = Path(str(dest) + ".part.json")

    if not ranges or size < BIG:
        # single connection, from scratch (small files or servers without Range)
        got = 0
        with _request(url) as r, open(part, "wb") as f:
            while True:
                if cancel and cancel():
                    raise DownloadError("annullato")
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                counter.add(len(chunk))
        if size and got != size:
            raise DownloadError(f"download incompleto: {got} di {size} byte")
    else:
        segs = [(i, off, min(off + SEGMENT, size) - 1) for i, off in enumerate(range(0, size, SEGMENT))]
        done = set()
        if part.exists() and meta.exists() and part.stat().st_size == size:
            try:
                m = json.loads(meta.read_text())
                if m.get("size") == size and m.get("url") == url:
                    done = set(m.get("done", []))
            except Exception:
                done = set()
        if not done or not part.exists() or part.stat().st_size != size:
            done = set()
            with open(part, "wb") as f:
                f.truncate(size)                # pre-allocated file: segments are written in place
        lock = threading.Lock()

        def save_meta() -> None:
            meta.write_text(json.dumps({"size": size, "url": url, "done": sorted(done)}))

        for i, a, b in segs:                    # segments already downloaded earlier
            if i in done:
                counter.add(b - a + 1)

        def fetch(seg: Tuple[int, int, int]) -> None:
            i, a, b = seg
            last: Optional[Exception] = None
            for attempt in range(5):
                if cancel and cancel():
                    raise DownloadError("annullato")
                try:
                    got = 0
                    with _request(url, (a, b)) as r, open(part, "r+b") as f:
                        f.seek(a)
                        while True:
                            chunk = r.read(1 << 16)
                            if not chunk:
                                break
                            f.write(chunk)
                            got += len(chunk)
                    if got != b - a + 1:
                        raise DownloadError(f"segmento {i} incompleto")
                    with lock:
                        done.add(i)
                        if len(done) % 8 == 0:
                            save_meta()
                    counter.add(got)
                    return
                except OSError as e:
                    if getattr(e, "errno", None) == 28:
                        raise                      # disk full: no point retrying
                    last = e
                except DownloadError as e:
                    last = e
                time.sleep(1 + attempt)
            raise DownloadError(f"segmento {i} non scaricato: {last}")

        todo = [s for s in segs if s[0] not in done]
        try:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                for fut in [ex.submit(fetch, s) for s in todo]:
                    fut.result()
        finally:
            save_meta()                         # the completed segments are needed for resuming

    if sha256 and sha256_of(part) != sha256.lower():
        part.unlink(missing_ok=True)
        meta.unlink(missing_ok=True)
        raise DownloadError("controllo SHA-256 non superato (file corrotto): riprovo da capo al prossimo tentativo")
    os.replace(part, dest)
    meta.unlink(missing_ok=True)


def download_many(items: List[Dict], folder: Path, workers: int = 6,
                  on_progress: Optional[Callable[[int, int], None]] = None,
                  cancel: Optional[Callable[[], bool]] = None) -> List[Path]:
    """items: [{'url':..., 'name':..., 'sha256':...}]. Downloads everything into folder.
    on_progress(bytes_downloaded, bytes_total)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=8) as ex:
        probes = list(ex.map(lambda it: probe(it["url"]), items))
    total = sum(p[0] for p in probes) or 1
    state = {"done": 0}

    def add(n: int) -> None:
        state["done"] += n
        if on_progress:
            on_progress(min(state["done"], total), total)

    counter_lock = threading.Lock()

    def cb(n: int) -> None:
        with counter_lock:
            add(n)

    jobs = list(zip(items, probes))
    small = [j for j in jobs if j[1][0] < BIG]
    big = sorted([j for j in jobs if j[1][0] >= BIG], key=lambda j: -j[1][0])

    def run(job) -> None:
        it, (size, rng) = job
        download_file(it["url"], folder / it["name"], size, rng, it.get("sha256"), workers, cb, cancel)

    if small:                                   # small files in parallel with each other
        with ThreadPoolExecutor(max_workers=6) as ex:
            for fut in [ex.submit(run, j) for j in small]:
                fut.result()
    for j in big:                               # each large file using all the connections
        run(j)
    return [folder / it["name"] for it in items]
