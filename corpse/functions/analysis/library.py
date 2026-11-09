"""Index of the photos and videos the user works with, kept like a small server database (SQLite).

Folders are *registered*, never copied: the index stores where they are (path), what they are (kind) and, on
request, facts about their files (size, resolution, frames...). Views and analyses read the original files.
Thumbnails are produced in memory on demand, so a preview never leaves a copy on disk.

Kinds: photo (flat folder of images), photo_stereo (rx/lx folders), video (one video), video_stereo (rx/lx videos).
Folders that already live in the default data folders (older installations) are registered in place.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from common.paths import LOCAL_DIR, PHOTO_DIR, STEREO_PHOTO_DIR, STEREO_VIDEO_DIR, VIDEO_DIR

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".m4v", ".mpg", ".mpeg"}
LEGACY_DIRS = {"photo": PHOTO_DIR, "photo_stereo": STEREO_PHOTO_DIR,
               "video": VIDEO_DIR, "video_stereo": STEREO_VIDEO_DIR}
KINDS = tuple(LEGACY_DIRS)
THUMB_CACHE_ITEMS = 256          # thumbnails kept in memory (never on disk)


@dataclass(frozen=True)
class Source:
    id: int
    kind: str
    name: str
    path: Path

    @property
    def exists(self) -> bool:
        return self.path.is_dir()


@dataclass(frozen=True)
class MediaInfo:
    """What a view needs to know about one file, read from the original (nothing is copied)."""
    path: Path
    kind: str                    # "image" | "video"
    size: int                    # bytes
    width: int
    height: int
    frames: int = 0              # videos
    fps: float = 0.0             # videos

    @property
    def duration(self) -> float:
        return self.frames / self.fps if self.fps else 0.0


class Library:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock, self._db:
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, name TEXT NOT NULL,
                    path TEXT NOT NULL, added REAL NOT NULL, UNIQUE (kind, path), UNIQUE (kind, name));
                CREATE TABLE IF NOT EXISTS media (
                    path TEXT PRIMARY KEY, size INTEGER NOT NULL, mtime REAL NOT NULL, kind TEXT NOT NULL,
                    width INTEGER, height INTEGER, frames INTEGER, fps REAL);
            """)
        self._thumbs: "OrderedDict[Tuple[str, int, float, int], bytes]" = OrderedDict()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ---- sources ------------------------------------------------------------------
    @staticmethod
    def _row(r: sqlite3.Row) -> Source:
        return Source(r["id"], r["kind"], r["name"], Path(r["path"]))

    def add_source(self, kind: str, folder: Path, name: Optional[str] = None) -> Source:
        """Registers `folder` (not copied). Registering the same folder twice returns the existing entry."""
        if kind not in KINDS:
            raise ValueError(f"Unknown kind: {kind}")
        folder = Path(folder).resolve()
        if not folder.is_dir():
            raise FileNotFoundError(f"Not a folder: {folder}")
        with self._lock, self._db:
            row = self._db.execute("SELECT * FROM sources WHERE kind=? AND path=?", (kind, str(folder))).fetchone()
            if row:
                return self._row(row)
            base = name or folder.name
            label, n = base, 2
            while self._db.execute("SELECT 1 FROM sources WHERE kind=? AND name=?", (kind, label)).fetchone():
                label, n = f"{base} ({n})", n + 1          # two different folders with the same name
            cur = self._db.execute("INSERT INTO sources (kind, name, path, added) VALUES (?,?,?,?)",
                                   (kind, label, str(folder), time.time()))
            return Source(cur.lastrowid, kind, label, folder)

    def sources(self, kind: str) -> List[Source]:
        """The registered folders of a kind (the default data folder is scanned first, in place)."""
        self.sync_legacy(kind)
        with self._lock:
            rows = self._db.execute("SELECT * FROM sources WHERE kind=? ORDER BY lower(name)", (kind,)).fetchall()
        return [self._row(r) for r in rows]

    def source(self, kind: str, name: str) -> Optional[Source]:
        with self._lock:
            row = self._db.execute("SELECT * FROM sources WHERE kind=? AND name=?", (kind, name)).fetchone()
        return self._row(row) if row else None

    def remove_source(self, source_id: int) -> None:
        """Forgets a folder. The files are never touched."""
        with self._lock, self._db:
            self._db.execute("DELETE FROM sources WHERE id=?", (source_id,))

    def sync_legacy(self, kind: str) -> None:
        """Registers, in place, the folders already inside the default data folder of this kind."""
        root = LEGACY_DIRS[kind]
        if not root.is_dir():
            return
        for f in sorted(root.iterdir()):
            if f.is_dir() and not f.name.startswith("."):
                self.add_source(kind, f)

    # ---- files -------------------------------------------------------------------------
    def files(self, source: Source) -> List[Path]:
        """Images or videos of a source, read from disk now (the folder is the truth, the index is a map)."""
        suffixes = IMAGE_SUFFIXES if source.kind.startswith("photo") else VIDEO_SUFFIXES
        if not source.path.is_dir():
            return []
        return sorted((p for p in source.path.rglob("*") if p.is_file() and p.suffix.lower() in suffixes),
                      key=lambda p: str(p).lower())

    def info(self, path: Path) -> MediaInfo:
        """Size, resolution and (videos) frames/fps of a file; cached by size+mtime, no pixel data is kept."""
        path = Path(path)
        st = path.stat()
        key = str(path.resolve())
        with self._lock:
            row = self._db.execute("SELECT * FROM media WHERE path=?", (key,)).fetchone()
        if row and row["size"] == st.st_size and row["mtime"] == st.st_mtime:
            return MediaInfo(path, row["kind"], st.st_size, row["width"], row["height"], row["frames"], row["fps"])
        mi = media_info(path)
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO media VALUES (?,?,?,?,?,?,?,?)",
                             (key, mi.size, st.st_mtime, mi.kind, mi.width, mi.height, mi.frames, mi.fps))
        return mi

    def thumbnail(self, path: Path, size: int = 140) -> bytes:
        """JPEG bytes of a thumbnail (first frame for a video), built in memory and kept in a small RAM cache."""
        path = Path(path)
        st = path.stat()
        key = (str(path), st.st_size, st.st_mtime, size)
        with self._lock:
            if key in self._thumbs:
                self._thumbs.move_to_end(key)
                return self._thumbs[key]
        data = thumbnail_bytes(path, size)
        with self._lock:
            self._thumbs[key] = data
            while len(self._thumbs) > THUMB_CACHE_ITEMS:
                self._thumbs.popitem(last=False)
        return data


def _is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_SUFFIXES


def media_info(path: Path) -> MediaInfo:
    path = Path(path)
    size = path.stat().st_size
    if _is_video(path):
        cap = cv2.VideoCapture(str(path))
        try:
            if not cap.isOpened():
                raise ValueError(f"Cannot open video: {path.name}")
            return MediaInfo(path, "video", size, int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                             int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                             float(cap.get(cv2.CAP_PROP_FPS)))
        finally:
            cap.release()
    img = _read_image(path)
    return MediaInfo(path, "image", size, img.shape[1], img.shape[0])


def _read_image(path: Path) -> "np.ndarray":
    img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)   # also non-ASCII paths on Windows
    if img is None:
        raise ValueError(f"Cannot read image: {path.name}")
    return img


def thumbnail_bytes(path: Path, size: int = 140) -> bytes:
    path = Path(path)
    if _is_video(path):
        cap = cv2.VideoCapture(str(path))
        try:
            ok, frame = cap.read()
        finally:
            cap.release()
        if not ok:
            raise ValueError(f"Cannot read video: {path.name}")
    else:
        frame = _read_image(path)
    h, w = frame.shape[:2]
    scale = size / max(h, w)
    if scale < 1:
        frame = cv2.resize(frame, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise ValueError("Cannot encode the thumbnail.")
    return buf.tobytes()


_default: Optional[Library] = None
_default_lock = threading.Lock()


def default_library() -> Library:
    """The application's library (datasets/Dataset_Locale/library.sqlite), opened once."""
    global _default
    with _default_lock:
        if _default is None:
            _default = Library(LOCAL_DIR / "library.sqlite")
        return _default
