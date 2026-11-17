"""Index of the photos and videos the user works with: the register of folders (see `common.media_library`) plus
what only an image library can tell - resolution, number of frames, thumbnails.

Folders are *registered*, never copied: the index stores where they are (path), what they are (kind) and, on
request, facts about their files (size, resolution, frames...). Views and analyses read the original files.
Thumbnails are produced in memory on demand, so a preview never leaves a copy on disk.

Kinds: photo (flat folder of images), photo_stereo (rx/lx folders), video (one video), video_stereo (rx/lx videos).
Folders that already live in the default data folders (older installations) are registered in place. The same
register is what "Folders > Local" shows, so a folder added there can be analysed straight away.

Autore: Samuele Gallo
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

from common.media_library import (KINDS, LEGACY_DIRS, LIBRARY_DB, Registry, Source,  # noqa: F401 - kept for the callers
                                  media_suffixes)
from common.params import IMAGE_SUFFIXES as _IMAGE_SUFFIXES, VIDEO_SUFFIXES as _VIDEO_SUFFIXES

IMAGE_SUFFIXES = set(_IMAGE_SUFFIXES)
VIDEO_SUFFIXES = set(_VIDEO_SUFFIXES)
THUMB_CACHE_ITEMS = 256          # thumbnails kept in memory (never on disk)


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


class Library(Registry):
    """The register of folders, able to read the media too."""

    def __init__(self, db_path: Path):
        super().__init__(db_path)
        self._thumbs: "OrderedDict[Tuple[str, int, float, int], bytes]" = OrderedDict()

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
            _default = Library(LIBRARY_DB)
        return _default
