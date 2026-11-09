"""Server folders with safe paths: one folder per area in store/library, uploads waiting in store/pending.

Common areas (photos, models, datasets):
  * "user"   : reads and downloads anywhere (except the model quarantine), CREATES new files and folders but does not
               overwrite, rename, move or delete anything.
  * "server" : everything, including approval of models uploaded by users.
  * A .pt/.onnx model uploaded by a user ends up in models/_pending/<user>/ until an administrator
    approves it: a .pt is a pickle archive and can execute code when loaded.
Personal area (mine): files/mine/<user>/ - the owner reads, writes, moves and deletes, within the quota.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple
from datetime import date

from common.errors import AppError
from common.params import AREA_MINE, AREA_PHOTOS, AREA_STEREO, AREAS, AREAS_MEDIA, KIND_AREA

KIND_OF_AREA = {area: kind for kind, area in KIND_AREA.items()}
from common.model_metadata import classes_from_data_yaml

from .params import (EXTENSIONS, LIBRARY_DIR, MAX_BYTES, MAX_BYTES_EXT, MINE_DIR, PENDING, PENDING_DIR_NAME, SPECIES_EXAMPLE,
                     SPECIES_RE, STORE_DIR, TMP, DATASET_EXAMPLE, LABEL_SUFFIX, SPECIES_IMAGE_EXT)
from .media_tree import CLASSES_FILE, check_media_file, count_media, move_numbered, validate_media_dir
from .dataset_tree import count_dataset_images, validate_dataset_dir

_MAGIC = {".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",), ".png": (b"\x89PNG\r\n\x1a\n",),
          ".bmp": (b"BM",), ".webp": (b"RIFF",), ".tif": (b"II*\x00", b"MM\x00*"), ".tiff": (b"II*\x00", b"MM\x00*")}
_WIN_RESERVED = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
_lock = threading.Lock()

QUARANTINE_AREAS = AREAS_MEDIA + ("models", "datasets")     # every shared area: uploads wait in store/pending/<area>
ADMIN_ONLY_AREAS = ()                                       # no area is closed for reading: only the pending uploads are


def is_quarantine(area: str, rel: str) -> bool:
    """True if rel is the pending folder of an area (or inside it)."""
    return area in QUARANTINE_AREAS and (rel == PENDING or rel.startswith(PENDING + "/"))


def clean_rel(rel: str) -> str:
    """Normalizes a relative path ('/' separator), rejecting anything that escapes the area."""
    rel = (rel or "").replace("\\", "/").strip("/")
    parts: List[str] = []
    for p in PurePosixPath(rel).parts if rel else ():
        if p in ("", "."):
            continue
        if p == ".." or ":" in p or "\x00" in p or p.startswith(TMP) or p.rstrip(". ").lower().split(".")[0] in _WIN_RESERVED:
            raise AppError("Invalid path.")
        if p != p.strip() or p.endswith(".") or len(p) > 120:
            raise AppError("Invalid name.")
        parts.append(p)
    return "/".join(parts)



def _retry(action, attempts: int = 5):
    """Runs `action`, trying again a few times when the file system answers "permission denied" / "in use".
    On Windows (and on folders synchronised by OneDrive or watched by an antivirus) a file can be locked for a
    moment right after it was written."""
    for n in range(attempts):
        try:
            return action()
        except PermissionError:
            if n == attempts - 1:
                raise
            time.sleep(0.2 * (n + 1))


def _replace(src: Path, dst: Path) -> None:
    _retry(lambda: os.replace(src, dst))


def _unlock(func, path, _exc) -> None:
    """rmtree callback: read-only files (common on Windows) are made writable and removed again."""
    try:
        os.chmod(path, 0o700)
        func(path)
    except OSError:
        pass


def _rmtree(path: Path) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_unlock)
    else:
        shutil.rmtree(path, onerror=_unlock)


def _remove_tree(path: Path, strict: bool = True) -> None:
    """Deletes a folder, with retries. With strict=False a folder that cannot be removed is left behind instead of
    raising: used for the leftovers of an operation that already succeeded."""
    try:
        _retry(lambda: _rmtree(path))
    except OSError:
        if strict:
            raise

class Storage:
    """`root` is the data folder; everything this class manages is inside `root/store`."""

    def __init__(self, root: Path):
        self.data_dir = Path(root).resolve()
        self.root = self.data_dir / STORE_DIR
        for a in QUARANTINE_AREAS:
            self.library(a).mkdir(parents=True, exist_ok=True)
            self.pending_root(a).mkdir(parents=True, exist_ok=True)
        (self.root / MINE_DIR).mkdir(parents=True, exist_ok=True)

    # ---- paths ----------------------------------------------------------
    def library(self, area: str) -> Path:
        """Folder of the approved items of an area."""
        return self.root / LIBRARY_DIR / area

    def pending_root(self, area: str) -> Path:
        """Folder of the uploads of an area that wait for review (one subfolder per user)."""
        return self.root / PENDING_DIR_NAME / area

    def base(self, area: str, owner: str) -> Path:
        if area not in AREAS:
            raise AppError("Unknown area.", 404)
        if area == AREA_MINE:
            if not owner:
                raise AppError("Unknown area.", 404)
            return self.root / MINE_DIR / owner
        return self.library(area)

    def pending_media_dir(self, username: str, species: str, kind: str) -> Path:
        """Folder of a user's upload for a species waiting for review; 404 if there is none."""
        if re.fullmatch(SPECIES_RE, species or "") and kind in KIND_AREA:
            folder = self.pending_root(KIND_AREA[kind]) / username / species
            if folder.is_dir():
                return folder
        raise AppError("No pending photos for this species.", 404)

    def resolve(self, area: str, rel: str, admin: bool, owner: str = "") -> Tuple[Path, str]:
        rel = clean_rel(rel)
        if not admin and (area in ADMIN_ONLY_AREAS or is_quarantine(area, rel)):
            raise AppError("Area reserved to administrators.", 403)
        if is_quarantine(area, rel):                          # "_pending/..." is the waiting uploads of this area
            base, sub = self.pending_root(area), rel[len(PENDING) + 1:]
        else:
            base, sub = self.base(area, owner), rel
        if area == AREA_MINE:
            base.mkdir(parents=True, exist_ok=True)
        path = (base / sub).resolve() if sub else base.resolve()
        if path != base.resolve() and base.resolve() not in path.parents:
            raise AppError("Invalid path.")
        return path, rel

    # ---- labels of approved photos ----------------------------------------
    def save_labels(self, area: str, media_rel: str, text: str, classes: Optional[str] = None) -> str:
        """Replaces the label file (and, if given, the class names) of an APPROVED photo of the library. Returns the
        path of the label file. Only photos can be edited here (a video would have to be downloaded whole)."""
        if area not in (AREA_PHOTOS, AREA_STEREO):
            raise AppError("Only the labels of photos can be edited on the server.", 422)
        rel = clean_rel(media_rel)
        if is_quarantine(area, rel):
            raise AppError("Approve the upload before editing its labels.", 409)
        media, _ = self.resolve(area, rel, True)
        if not media.is_file() or media.suffix.lower() not in SPECIES_IMAGE_EXT:
            raise AppError("Resource not found.", 404)
        if len(text.encode("utf-8")) > MAX_BYTES_EXT[(area, LABEL_SUFFIX)] or \
                (classes is not None and len(classes.encode("utf-8")) > 1 << 16):
            raise AppError("File too large.", 413)
        self._write_text(media.with_suffix(LABEL_SUFFIX), text)
        if classes is not None:
            self._write_text(media.parent / CLASSES_FILE, classes)
        return str(PurePosixPath(rel).with_suffix(LABEL_SUFFIX))

    @staticmethod
    def _write_text(path: Path, text: str) -> None:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        _replace(tmp, path)

    # ---- quota -------------------------------------------------------------
    def usage(self, owner: str) -> int:
        base = self.base(AREA_MINE, owner)
        if not base.exists():
            return 0
        return sum(p.stat().st_size for p in base.rglob("*") if p.is_file() and not p.is_symlink())

    # ---- reading -----------------------------------------------------------
    def list_dir(self, area: str, rel: str, admin: bool, owner: str = "") -> Dict[str, Any]:
        path, rel = self.resolve(area, rel, admin, owner)
        if not path.is_dir():
            raise AppError("Folder not found.", 404)
        entries = []
        for p in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name.startswith(TMP) or p.is_symlink():
                continue
            child = f"{rel}/{p.name}" if rel else p.name
            if not admin and is_quarantine(area, child):
                continue
            st = p.stat()
            entries.append({"name": p.name, "type": "dir" if p.is_dir() else "file",
                            "size": 0 if p.is_dir() else st.st_size, "mtime": st.st_mtime})
        if admin and not rel and area in QUARANTINE_AREAS and self.pending_root(area).is_dir() and any(self.pending_root(area).iterdir()):
            entries.insert(0, {"name": PENDING, "type": "dir", "size": 0, "mtime": 0})    # the waiting uploads
        return {"area": area, "path": rel, "entries": entries}

    def open_file(self, area: str, rel: str, admin: bool, owner: str = "") -> Tuple[Path, int]:
        path, _ = self.resolve(area, rel, admin, owner)
        if not path.is_file() or path.is_symlink():
            raise AppError("File not found.", 404)
        return path, path.stat().st_size

    # ---- upload -------------------------------------------------------
    def check_new_file(self, area: str, rel: str, admin: bool, username: str, size: int,
                       quota_mb: int = 0) -> Tuple[Path, str]:
        """Validates an upload BEFORE receiving the data; returns (destination, effective path)."""
        rel = clean_rel(rel)
        if not rel:
            raise AppError("Specify the file name.")
        ext = PurePosixPath(rel).suffix.lower()
        if area not in EXTENSIONS:
            raise AppError("Unknown area.", 404)
        if ext not in EXTENSIONS[area]:
            raise AppError("Extension {ext} is not allowed in this area.", 415, ext=ext or "(none)")
        if size <= 0:
            raise AppError("Empty file or missing size.", 411)
        if size > MAX_BYTES_EXT.get((area, ext), MAX_BYTES[area]):
            raise AppError("File too large for this area.", 413)
        if area == "models" and not admin:
            if rel.startswith(PENDING + "/"):
                rel = rel[len(PENDING) + 1:]
            parts = rel.split("/")
            if len(parts) < 2 or not re.fullmatch(SPECIES_RE, parts[0]):
                raise AppError("Models go in a folder named after the scientific name (Genus species), "
                               "for example {example}.", 422, example=SPECIES_EXAMPLE)
        elif area in AREAS_MEDIA:
            check_media_file(KIND_OF_AREA[area], rel)                # structure and file type, for everyone
        elif area == "datasets" and not admin and "/" not in rel:
            raise AppError("A dataset goes in a folder with images, labels and data.yaml, "
                           "for example {example}.", 422, example=DATASET_EXAMPLE)
        if area in AREAS_MEDIA or (area in QUARANTINE_AREAS and not admin):
            rel = f"{PENDING}/{username}/{rel}"                      # waits until an administrator approves
        path, rel = self.resolve(area, rel, True if area != AREA_MINE else False, username)
        if area == AREA_MINE:
            old = path.stat().st_size if path.is_file() else 0
            if self.usage(username) - old + size > quota_mb * (1 << 20):
                raise AppError("Not enough space in your folder (quota {mb} MB).", 413, mb=quota_mb)
        return path, rel

    def tmp_path(self, area: str, owner: str = "") -> Path:
        d = self.base(area, owner) / TMP
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{os.getpid()}_{threading.get_ident()}_{time.time_ns()}"

    def commit_upload(self, tmp: Path, dest: Path, area: str, admin: bool) -> None:
        """Moves the received file into place. In common areas the user cannot overwrite."""
        ext = dest.suffix.lower()
        if ext in _MAGIC:
            with open(tmp, "rb") as f:
                head = f.read(16)
            if not any(head.startswith(m) for m in _MAGIC[ext]):
                raise AppError("The content does not match the declared image type.", 415)
        with _lock:
            if dest.exists() and not (admin or area == AREA_MINE):
                raise AppError("A file with this name already exists (you cannot overwrite it).", 409)
            if dest.is_dir():
                raise AppError("A folder with this name already exists.", 409)
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp, dest)

    def mkdir(self, area: str, rel: str, admin: bool, username: str) -> str:
        path, rel = self.resolve(area, rel, admin, username)
        if not rel:
            raise AppError("Specify the folder name.")
        if area in QUARANTINE_AREAS and not admin:
            raise AppError("Users cannot create folders in this area.", 403)
        with _lock:
            if path.exists():
                raise AppError("Already exists.", 409)
            path.mkdir(parents=True)
        return rel

    # ---- editing ----------------------------------------------------------
    def delete(self, area: str, rel: str, owner: str = "") -> None:
        path, rel = self.resolve(area, rel, True, owner)
        if not rel:
            raise AppError("The root of an area cannot be deleted.")
        if area in QUARANTINE_AREAS and rel == PENDING:
            raise AppError("The quarantine area is protected.")
        if not path.exists():
            raise AppError("Does not exist.", 404)
        quarantined = area in QUARANTINE_AREAS and rel.startswith(PENDING + "/")
        is_file = path.is_file()
        _remove_tree(path) if path.is_dir() else path.unlink()
        if quarantined:
            if is_file and area == "models" and path.suffix.lower() != ".json":
                path.with_suffix(".json").unlink(missing_ok=True)       # i metadati seguono il modello
            self._prune_quarantine(area, path.parent)

    def move(self, area: str, src: str, dst: str, owner: str = "") -> str:
        s, src = self.resolve(area, src, True, owner)
        d, dst = self.resolve(area, dst, True, owner)
        if not src or not dst:
            raise AppError("Missing paths.")
        if not s.exists():
            raise AppError("Source not found.", 404)
        if d.exists():
            raise AppError("The destination already exists.", 409)
        if d == s or s in d.parents:
            raise AppError("Invalid move.")
        d.parent.mkdir(parents=True, exist_ok=True)
        _replace(s, d)
        return dst

    def approve_model(self, rel: str, new_name: Optional[str] = None) -> str:
        """Moves a model from models/_pending/<user>/<species>/x.pt to models/<species>/x.pt,
        together with its metadata file (x.json) if there is one."""
        rel = clean_rel(rel)
        if not rel.startswith(PENDING + "/"):
            raise AppError("The file is not in quarantine.")
        name = clean_rel(new_name) if new_name else "/".join(rel.split("/")[2:])      # keeps the species folder
        if not name:
            raise AppError("Missing paths.")
        sidecar = self._sidecar(rel, name)                  # controllato PRIMA: o si sposta tutto o niente
        dst = self.move("models", rel, name)
        if sidecar:
            self.move("models", *sidecar)
        self._prune_quarantine("models", self.resolve("models", rel, True)[0].parent)
        return dst

    def _sidecar(self, rel: str, name: str) -> Optional[Tuple[str, str]]:
        """I metadati (.json) di un modello in quarantena, con la loro destinazione; None se non ci sono
        (o se il file stesso è un .json). Se la destinazione è occupata, errore prima di spostare qualsiasi cosa."""
        if PurePosixPath(rel).suffix.lower() == ".json":
            return None
        src = str(PurePosixPath(rel).with_suffix(".json"))
        dst = str(PurePosixPath(name).with_suffix(".json"))
        path, _ = self.resolve("models", src, True)
        if not path.is_file():
            return None
        target, _ = self.resolve("models", dst, True)
        if target.exists():
            raise AppError("The destination already exists.", 409)
        return src, dst
    
    def _prune_quarantine(self, area: str, folder: Path) -> None:
        """After a move or a delete among the pending uploads, removes the folders left empty, from the bottom
        up; it stops at the pending folder of the area (which stays) and never goes beyond."""
        root = self.pending_root(area)
        while root in folder.parents:
            try:
                folder.rmdir()
            except OSError:
                return                                  # not empty (or already gone): stop here
            folder = folder.parent

    def _remove_pending(self, area: str, src: Path) -> None:
        """Deletes a pending folder and the empty folders above it. Call with _lock held."""
        _remove_tree(src, strict=False)                 # the work is already done: a locked leftover must not undo it
        self._prune_quarantine(area, src.parent)

    def approve_media(self, username: str, species: str, kind: str, day: date) -> Tuple[str, int]:
        """Approves an upload: moves its files, numbered, to library/<area>/<species>/<species>_<user>_<day> and
        removes what is left in the pending folder. Returns (folder name, number of media files)."""
        area = KIND_AREA[kind]
        src = self.pending_media_dir(username, species, kind)
        errors = validate_media_dir(src, kind)              # after the upload the user may have changed the files
        if errors:
            raise errors[0]
        parent = self.library(area) / species
        with _lock:
            parent.mkdir(exist_ok=True)
            base = f"{species}_{username}_{day.isoformat()}"
            final, n = parent / base, 2
            while final.exists():
                final = parent / f"{base}_{n}"
                n += 1
            work = parent / (TMP + final.name)              # working folder, invisible to the users
            _remove_tree(work, strict=False)                # leftovers of an interrupted attempt
            try:
                count = move_numbered(src, work, kind)
                _replace(work, final)
            finally:
                _remove_tree(work, strict=False)
            self._remove_pending(area, src)
        return final.name, count

    def reject_media(self, username: str, species: str, kind: str) -> int:
        """Rejects an upload: deletes its files. Returns how many media files were deleted."""
        src = self.pending_media_dir(username, species, kind)
        count = count_media(src, kind)
        with _lock:
            self._remove_pending(KIND_AREA[kind], src)
        return count

    def pending_dataset_dir(self, username: str, name: str, admin: bool = False) -> Path:
        """Folder of a dataset waiting for review (an admin's one is already among the server datasets); 404 if there is nothing."""
        if not name or "/" in name or name.startswith((".", "_")):
            raise AppError("Invalid dataset name.", 422)
        folder = self.library("datasets") / name if admin else self.pending_root("datasets") / username / name
        if not folder.is_dir():
            raise AppError("No pending dataset with this name.", 404)
        return folder

    def approve_dataset(self, username: str, name: str, final: Optional[str] = None) -> Tuple[str, int]:
        """Publishes the dataset of a user among the server datasets, after checking it again.
        With `final` it takes that name (a number is added if it is taken); without it, it keeps `name` or fails.
        Returns (final name, number of images)."""
        src = self.pending_dataset_dir(username, name)
        errors = validate_dataset_dir(src)
        if errors:
            raise errors[0]
        base = self.library("datasets")
        with _lock:
            dst = base / (final or name)
            if final:
                n = 2
                while dst.exists():
                    dst = base / f"{final}_{n}"
                    n += 1
            elif dst.exists():
                raise AppError("A dataset with this name already exists.", 409)
            dst.parent.mkdir(parents=True, exist_ok=True)
            _replace(src, dst)
            self._prune_quarantine("datasets", src.parent)
        return dst.relative_to(base).as_posix(), count_dataset_images(dst)

    def reject_dataset(self, username: str, name: str) -> int:
        """Removes the dataset waiting for review. Returns how many images it had."""
        src = self.pending_dataset_dir(username, name)
        count = count_dataset_images(src)
        with _lock:
            _remove_tree(src)
            self._prune_quarantine("datasets", src.parent)
        return count
    
    def dataset_classes(self, name: str, pending_user: Optional[str] = None) -> List[str]:
        """The species declared in the data.yaml of a dataset (published, or waiting if `pending_user` is given)."""
        folder = (self.pending_root("datasets") / pending_user / name if pending_user
                  else self.library("datasets") / name)
        for f in ("data.yaml", "data.yml"):
            if (folder / f).is_file():
                return classes_from_data_yaml(folder / f)
        return []
    
    def pending_model_path(self, username: str, species: str, file: str, admin: bool = False) -> str:
        """Path (inside the models area) of a model waiting for review (an admin's one is already published); 404 if it is not there."""
        for part in (species, file):
            if not part or "/" in part or part.startswith((".", "_")):
                raise AppError("Invalid path.")
        rel = f"{species}/{file}" if admin else f"{PENDING}/{username}/{species}/{file}"
        path, _ = self.resolve("models", rel, True)
        if not path.is_file():
            raise AppError("No pending model with this name.", 404)
        return rel
    
