"""One-time conversion of the data folder from the previous layout to `store/` (see server/params.py).

The history (submissions: who uploaded, who approved, when) stays in the database and is kept; only the files move.
Everything is idempotent: running it again does nothing once the old folders are gone, and an interrupted run
continues where it stopped. Only what the old server owned is moved: the folders of the app's own local data that
happen to live in the same data folder are never touched."""
from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path
from typing import List

from common.params import KIND_AREA, KIND_DATASET, KIND_PHOTOS, KIND_STEREO, LOCAL_FOLDER_NAMES, STEREO_SIDES

from .db import Database
from .params import LIBRARY_DIR, MINE_DIR, PENDING, PENDING_DIR_NAME, SPECIES_RE, STORE_DIR, SUBMISSION_APPROVED, TMP
from .storage import _replace, _remove_tree

log = logging.getLogger("server.migrate")


def _move(src: Path, dst: Path, notes: List[str]) -> None:
    """Moves a file or a folder; into an existing folder it merges, and a file that already exists is left alone."""
    if not src.exists():
        return
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        _replace(src, dst)
        return
    if src.is_dir() and dst.is_dir():
        for child in sorted(src.iterdir()):
            _move(child, dst / child.name, notes)
        try:
            src.rmdir()
        except OSError:
            pass
        return
    notes.append(f"left in place (the destination exists): {src}")


def _rmdir_if_empty(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass


def _is_stereo(folder: Path) -> bool:
    return any((folder / s).is_dir() for s in STEREO_SIDES)


def _has_files(folder: Path) -> bool:
    return any(p.is_file() for p in folder.rglob("*"))


def _migrate_species(old: Path, store: Path, db: Database, notes: List[str]) -> None:
    """dataset_Specie/<species>/<upload> and dataset_Specie/_pending/<user>/<species> -> photos or stereo."""
    for item in sorted(old.iterdir()):
        if item.name.startswith(TMP):
            _remove_tree(item, strict=False)
        elif item.name == PENDING:
            for user in sorted(p for p in item.iterdir() if p.is_dir()):
                for folder in sorted(p for p in user.iterdir() if p.is_dir()):
                    kind = KIND_STEREO if _is_stereo(folder) else KIND_PHOTOS
                    _move(folder, store / PENDING_DIR_NAME / KIND_AREA[kind] / user.name / folder.name, notes)
                    if kind != KIND_PHOTOS:
                        db.set_submission_kind(KIND_PHOTOS, f"{PENDING}/{user.name}/{folder.name}", kind, "pending")
                _rmdir_if_empty(user)
            _rmdir_if_empty(item)
        elif item.is_dir() and re.fullmatch(SPECIES_RE, item.name):
            for batch in sorted(p for p in item.iterdir() if p.is_dir() and not p.name.startswith(TMP)):
                kind = KIND_STEREO if _is_stereo(batch) else KIND_PHOTOS
                _move(batch, store / LIBRARY_DIR / KIND_AREA[kind] / item.name / batch.name, notes)
                if kind != KIND_PHOTOS:
                    db.set_submission_kind(KIND_PHOTOS, f"{item.name}/{batch.name}", kind, SUBMISSION_APPROVED)
            for leftover in item.glob(TMP + "*"):
                _remove_tree(leftover, strict=False)
            _rmdir_if_empty(item)
        else:
            notes.append(f"not recognised, left in place: {item}")
    _rmdir_if_empty(old)


def _migrate_models(old: Path, store: Path, notes: List[str]) -> None:
    """models/_pending and the species folders of models/ -> library/models. Other files of the folder (the
    app's own local models) stay where they are."""
    _move(old / PENDING, store / PENDING_DIR_NAME / "models", notes)
    for item in sorted(old.iterdir()) if old.is_dir() else []:
        if item.is_dir() and re.fullmatch(SPECIES_RE, item.name):
            _move(item, store / LIBRARY_DIR / "models" / item.name, notes)


def _migrate_datasets(old: Path, store: Path, db: Database, notes: List[str]) -> None:
    """dataset_Training/_pending and the datasets the database says were approved -> library/datasets."""
    _move(old / PENDING, store / PENDING_DIR_NAME / "datasets", notes)
    for row in db.list_submissions(status=SUBMISSION_APPROVED, kind=KIND_DATASET):
        rel = Path(row["path"])
        if (old / rel).is_dir():
            _move(old / rel, store / LIBRARY_DIR / "datasets" / rel, notes)
            parent = (old / rel).parent
            if parent != old:
                _rmdir_if_empty(parent)


def migrate_legacy(data_dir: Path, db: Database) -> List[str]:
    """Moves the files of the previous layout into `data_dir/store`. Returns notes about what was left in place."""
    data_dir = Path(data_dir)
    store = data_dir / STORE_DIR
    notes: List[str] = []
    names = LOCAL_FOLDER_NAMES
    if (data_dir / names["species"]).is_dir():
        _migrate_species(data_dir / names["species"], store, db, notes)
    if (data_dir / names["models"]).is_dir():
        _migrate_models(data_dir / names["models"], store, notes)
    if (data_dir / names["training"]).is_dir():
        _migrate_datasets(data_dir / names["training"], store, db, notes)
    users = data_dir / names["users"]
    if users.is_dir():
        for home in sorted(p for p in users.iterdir() if p.is_dir()):
            _move(home, store / MINE_DIR / home.name, notes)
        _rmdir_if_empty(users)
    for note in notes:
        log.warning("migration: %s", note)
    return notes


# What belongs to the server and used to live beside the app's own data folders.
SERVER_ITEMS = ("server.db", "server.db-wal", "server.db-shm", STORE_DIR, "logs", "backups", "admin_key.txt",
                "admin_key", TMP)


def adopt_local_server_data(local_dir: Path, data_dir: Path) -> List[str]:
    """Moves the server's own files out of the app's local data folder into `data_dir` (a folder of its own).

    Only the items listed in SERVER_ITEMS move; the app's folders (photos, models, training sets...) stay where they
    are. It runs once: nothing happens when the folders are the same, when there is nothing to move or when `data_dir`
    already holds a database."""
    local_dir, data_dir = Path(local_dir), Path(data_dir)
    notes: List[str] = []
    if local_dir.resolve() == data_dir.resolve() or not (local_dir / "server.db").is_file():
        return notes
    if (data_dir / "server.db").exists():
        notes.append(f"{data_dir} already has a database: the one in {local_dir} was left in place")
        log.warning("migration: %s", notes[-1])
        return notes
    # files of the oldest layout are first brought into store/ (idempotent), then everything moves together
    migrate_legacy(local_dir, Database(local_dir / "server.db"))
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in SERVER_ITEMS:
        src = local_dir / name
        if src.exists():
            _move(src, data_dir / name, notes)
    for note in notes:
        log.warning("migration: %s", note)
    log.info("server data moved from %s to %s", local_dir, data_dir)
    return notes
