"""Register of the folders the user works with: where they are, what kind of media they hold.

Folders are *registered*, never copied: the index (SQLite) only stores the path and the kind, so the folder the
user chooses in "Folders > Local" is the very same folder the analysis pages offer. The files keep their own
names - there is no naming convention - and label files already sitting next to them are left alone.

Qt-free and without image libraries, so the interface, the analysis and the tests can all use it. Reading pixels
(resolution, thumbnails) is added on top of this by `corpse.functions.analysis.library`.

Autore: Samuele Gallo
"""
from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from common.params import IMAGE_SUFFIXES, VIDEO_SUFFIXES
from common.paths import LOCAL_DIR, PHOTO_DIR, STEREO_PHOTO_DIR, STEREO_VIDEO_DIR, VIDEO_DIR

KIND_PHOTO, KIND_PHOTO_STEREO = "photo", "photo_stereo"
KIND_VIDEO, KIND_VIDEO_STEREO = "video", "video_stereo"
LEGACY_DIRS = {KIND_PHOTO: PHOTO_DIR, KIND_PHOTO_STEREO: STEREO_PHOTO_DIR,
               KIND_VIDEO: VIDEO_DIR, KIND_VIDEO_STEREO: STEREO_VIDEO_DIR}
KINDS = tuple(LEGACY_DIRS)
LIBRARY_DB = LOCAL_DIR / "library.sqlite"


@dataclass(frozen=True)
class Source:
    id: int
    kind: str
    name: str
    path: Path

    @property
    def exists(self) -> bool:
        return self.path.is_dir()


def media_suffixes(kind: str) -> set:
    """The files that count for a kind: images for the photos, videos for the videos."""
    return set(IMAGE_SUFFIXES) if kind.startswith("photo") else set(VIDEO_SUFFIXES)


class Registry:
    """The folders, kept in a small database. Nothing here reads the media itself."""

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

    def source_of(self, path: Path) -> Optional[Source]:
        """The registered folder a file belongs to, if any."""
        path = Path(path).resolve()
        with self._lock:
            rows = self._db.execute("SELECT * FROM sources").fetchall()
        for r in rows:
            folder = Path(r["path"])
            if path == folder or folder in path.parents:
                return self._row(r)
        return None

    def rename_source(self, source_id: int, name: str) -> None:
        """Changes the name shown in the lists. The folder on disk keeps its own name."""
        with self._lock, self._db:
            self._db.execute("UPDATE sources SET name=? WHERE id=?", (name, source_id))

    def move_source(self, source_id: int, folder: Path) -> None:
        """Follows a folder that has been moved or renamed on disk."""
        with self._lock, self._db:
            self._db.execute("UPDATE sources SET path=? WHERE id=?", (str(Path(folder).resolve()), source_id))

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
        suffixes = media_suffixes(source.kind)
        if not source.path.is_dir():
            return []
        return sorted((p for p in source.path.rglob("*") if p.is_file() and p.suffix.lower() in suffixes),
                      key=lambda p: str(p).lower())


_default: Optional[Registry] = None
_default_lock = threading.Lock()


def default_registry() -> Registry:
    """The application's register of folders (datasets/Dataset_Locale/library.sqlite), opened once."""
    global _default
    with _default_lock:
        if _default is None:
            _default = Registry(LIBRARY_DB)
        return _default
