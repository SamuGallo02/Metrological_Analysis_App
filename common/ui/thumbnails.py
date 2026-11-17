"""Small previews of the photos (and of the videos already on this computer) shown as the icon of a row.

The server cannot make them — it has no image library — so the application makes them itself, once: the file is
read, scaled down and kept in a cache folder, so opening the same folder again costs nothing. Requests are served a
few at a time in the background and only for the rows the user is looking at, so a folder with a thousand photos
does not download a thousand files.

Autore: Samuele Gallo
"""
from __future__ import annotations

import atexit
import hashlib
from pathlib import Path
from typing import Callable, Dict, Optional, Union

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap

from common.params import IMAGE_SUFFIXES, VIDEO_SUFFIXES
from common.paths import LOCAL_DIR

THUMB_SIZE = 64
CACHE_DIR = LOCAL_DIR / "thumbs"
MAX_ICONS = 2000                            # previews kept in memory at the same time
MAX_SOURCE_BYTES = 40 << 20                 # a file bigger than this is not downloaded just to make an icon
Fetch = Callable[[str], bytes]              # key -> bytes of the file
_CACHES: "list" = []                        # every cache made: keeps them alive while their jobs run


def can_preview(name: str) -> bool:
    return Path(name).suffix.lower() in set(IMAGE_SUFFIXES)


def is_video(name: str) -> bool:
    return Path(name).suffix.lower() in set(VIDEO_SUFFIXES)


def _cache_file(key: str, size: int, variant: str = "") -> Path:
    name = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{name}_{size}{('_' + variant) if variant else ''}.png"


def thumbnail_from_bytes(data: bytes, size: int = THUMB_SIZE) -> Optional[QImage]:
    image = QImage()
    if not data or not image.loadFromData(data) or image.isNull():
        return None
    return image.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


def thumbnail_of_file(path: Union[str, Path], size: int = THUMB_SIZE) -> Optional[QImage]:
    """Preview of a file of this computer: a photo, or the first frame of a video (if OpenCV is there)."""
    path = Path(path)
    if can_preview(path.name):
        try:
            return thumbnail_from_bytes(path.read_bytes(), size)
        except OSError:
            return None
    if not is_video(path.name):
        return None
    try:
        import cv2                                       # only for videos: the GUI does not need it otherwise
        cap = cv2.VideoCapture(str(path))
        ok, frame = cap.read()
        cap.release()
        if not ok:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        image = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        return image.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    except Exception:                                     # noqa: BLE001 - a missing preview is not an error
        return None


class _Job(QRunnable):
    def __init__(self, cache: "ThumbnailCache", key: str):
        super().__init__()
        self.cache, self.key = cache, key
        self.setAutoDelete(True)

    def run(self) -> None:
        image = None
        try:
            data = self.cache.fetch(self.key)
            if data and len(data) <= MAX_SOURCE_BYTES:
                image = thumbnail_from_bytes(data, self.cache.size)
            if image is not None and self.cache.decorate is not None:
                image = self.cache.decorate(self.key, image)     # the labels drawn over the preview
        except Exception:                                 # noqa: BLE001 - offline, deleted file, broken image
            image = None
        if image is not None:
            try:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                image.save(str(_cache_file(self.key, self.cache.size, self.cache.variant)), "PNG")
            except OSError:
                pass
        self.cache._done(self.key, image)


class ThumbnailCache(QObject):
    """`fetch(key)` returns the bytes of the file; `ready(key, icon)` arrives in the GUI thread when its preview
    is there. Ask for a preview with `icon(key)`: it returns at once what is already known, and otherwise starts
    the work in the background."""

    ready = Signal(str, QIcon)
    _loaded = Signal(str, QImage)

    def __init__(self, fetch: Fetch, size: int = THUMB_SIZE, parent: Optional[QObject] = None, workers: int = 3,
                 decorate: Optional[Callable[[str, QImage], QImage]] = None, variant: str = ""):
        # No Qt parent on purpose: a job running in the background would otherwise write to an object the window
        # has already destroyed. The cache stays alive in _CACHES until its jobs are over.
        super().__init__()
        _CACHES.append(self)
        self.fetch, self.size = fetch, size
        self.decorate, self.variant = decorate, variant   # what is drawn over a preview, and its name in the cache
        self._icons: Dict[str, Optional[QIcon]] = {}      # key -> icon, or None while it is being made / failed
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(1, workers))
        self._loaded.connect(self._store)

    def icon(self, key: str) -> Optional[QIcon]:
        """The preview of a file: ready (an icon), or None — then it is asked for and `ready` will carry it."""
        if key in self._icons:
            return self._icons[key]
        cached = _cache_file(key, self.size, self.variant)
        if cached.is_file():
            icon = QIcon(QPixmap(str(cached)))
            self._icons[key] = icon
            return icon
        self._icons[key] = None                           # being made: do not ask twice
        self._pool.start(_Job(self, key))
        return None

    def _trim(self) -> None:
        while len(self._icons) > MAX_ICONS:                       # keeps the memory of a long session bounded
            self._icons.pop(next(iter(self._icons)))

    def forget(self, key: str) -> None:
        self._icons.pop(key, None)

    def set_variant(self, variant: str, decorate: Optional[Callable[[str, QImage], QImage]] = None) -> None:
        """Changes what is drawn over the previews (the labels on or off): each variant has its own cache, so
        going back and forth costs nothing."""
        if variant == self.variant:
            return
        self.variant, self.decorate = variant, decorate
        self._icons.clear()

    def _done(self, key: str, image: Optional[QImage]) -> None:
        self._loaded.emit(key, image if image is not None else QImage())

    def _store(self, key: str, image: QImage) -> None:
        if image.isNull():
            return                                        # no preview for this file: the row keeps its normal icon
        icon = QIcon(QPixmap.fromImage(image))
        self._icons[key] = icon
        self._trim()
        self.ready.emit(key, icon)

    def size_hint(self) -> QSize:
        return QSize(self.size, self.size)


@atexit.register
def _stop_every_cache() -> None:
    """Waits for the previews still being made: a job that wrote while Qt is closing would crash the application."""
    for cache in _CACHES:
        try:
            cache._pool.clear()
            cache._pool.waitForDone(2000)
        except RuntimeError:                      # already gone
            pass
