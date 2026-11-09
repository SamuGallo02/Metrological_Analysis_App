"""Registrazione di un invio di foto di specie, dopo la fine del caricamento."""
from __future__ import annotations
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

from common.errors import AppError

from .db import Database
from .params import (SPECIES_RE, PENDING, SUBMISSION_APPROVED, SUBMISSION_PENDING, SUBMISSION_REJECTED, KIND_PHOTOS,
                     KIND_DATASET, KIND_MODEL, KINDS_MEDIA)
from .media_tree import count_media, validate_media_dir
from .storage import Storage
from .dataset_tree import count_dataset_images, validate_dataset_dir


def submit_species(store: Storage, db: Database, username: str, species: str, kind: str = KIND_PHOTOS,
                   admin: bool = False) -> Dict[str, Any]:
    """Registers the photos / stereo photos / videos a user uploaded for a species. What an administrator
    sends is approved at once, by the administrator."""
    if kind not in KINDS_MEDIA:
        raise AppError("Unknown kind of upload.", 422)
    folder = store.pending_media_dir(username, species, kind)       # 404 if there is nothing waiting
    errors = validate_media_dir(folder, kind)
    if errors:
        raise errors[0]                                            # refused: no row is created
    path = f"{PENDING}/{username}/{species}"
    _check_not_waiting(db, username, path, kind)
    items = count_media(folder, kind)
    sid = db.add_submission(username, species, path, items, kind=kind)
    result = {"id": sid, "kind": kind, "species": species, "path": path, "photos": items, "pending": not admin}
    if admin:
        approve_submission(store, db, sid, username)
        result["pending"] = False
    return result

def _check_not_waiting(db: Database, username: str, path: str, kind: Optional[str] = None) -> None:
    for s in db.list_submissions(username=username, status=SUBMISSION_PENDING):
        if s["path"] == path and (kind is None or s["kind"] == kind):
            raise AppError("You already have a pending submission for this item.", 409)


def _record(db: Database, username: str, subject: str, path: str, items: int, kind: str, admin: bool) -> int:
    """Registers the submission. What an administrator publishes is approved at once, by the administrator."""
    _check_not_waiting(db, username, path, kind)
    sid = db.add_submission(username, subject, path, items, kind=kind)
    if admin:
        db.review_submission(sid, SUBMISSION_APPROVED, username)
    return sid


def submit_dataset(store: Storage, db: Database, username: str, name: str, admin: bool = False) -> Dict[str, Any]:
    folder = store.pending_dataset_dir(username, name, admin)      # 404 se non c'è nulla da inviare
    errors = validate_dataset_dir(folder)
    if errors:
        raise errors[0]                                            # rifiuta: nessuna riga viene creata
    path = name if admin else f"{PENDING}/{username}/{name}"
    images = count_dataset_images(folder)
    sid = _record(db, username, name, path, images, KIND_DATASET, admin)
    return {"id": sid, "kind": KIND_DATASET, "name": name, "path": path, "images": images, "pending": not admin}


def submit_model(store: Storage, db: Database, username: str, species: str, file: str, admin: bool = False) -> Dict[str, Any]:
    path = store.pending_model_path(username, species, file, admin)   # 404 se il file non è stato caricato
    sid = _record(db, username, species, path, 1, KIND_MODEL, admin)
    return {"id": sid, "kind": KIND_MODEL, "species": species, "file": file, "path": path, "pending": not admin}

def _pending_submission(db: Database, sid: int) -> Dict[str, Any]:
    sub = db.get_submission(sid)                                     # 404 se non esiste
    if sub["status"] != SUBMISSION_PENDING:
        raise AppError("This submission has already been reviewed.", 409)
    return sub

def _dataset_final_name(store: Storage, sub: Dict[str, Any]) -> str:
    """<species>/<species>_<user>_<date>. With one species in data.yaml that is it; with several (or none that is a proper
    scientific name) the name chosen by the user is used instead."""
    classes = store.dataset_classes(sub["species"], sub["username"])
    base = classes[0] if len(classes) == 1 and re.fullmatch(SPECIES_RE, classes[0]) else sub["species"]
    day = datetime.fromtimestamp(sub["created"]).date().isoformat()
    return f"{base}/{base}_{sub['username']}_{day}"

def approve_submission(store: Storage, db: Database, sid: int, reviewer: str) -> Dict[str, Any]:
    sub = _pending_submission(db, sid)
    if sub["kind"] == KIND_DATASET:
        name, images = store.approve_dataset(sub["username"], sub["species"], _dataset_final_name(store, sub))
        db.review_submission(sid, SUBMISSION_APPROVED, reviewer, path=name, photos=images)
        return {"id": sid, "kind": KIND_DATASET, "name": name, "images": images}
    if sub["kind"] == KIND_MODEL:
        final = store.approve_model(sub["path"])                   # il modello e il suo .json si spostano insieme
        db.review_submission(sid, SUBMISSION_APPROVED, reviewer, path=final)
        return {"id": sid, "kind": KIND_MODEL, "path": final}
    day = datetime.fromtimestamp(sub["created"]).date()              # the date of the upload
    folder, photos = store.approve_media(sub["username"], sub["species"], sub["kind"], day)
    db.review_submission(sid, SUBMISSION_APPROVED, reviewer,     # solo se i file sono andati a posto
                         path=f"{sub['species']}/{folder}", photos=photos)
    return {"id": sid, "kind": sub["kind"], "species": sub["species"], "folder": folder, "photos": photos}

def reject_submission(store: Storage, db: Database, sid: int, reviewer: str) -> Dict[str, Any]:
    sub = _pending_submission(db, sid)
    if sub["kind"] == KIND_DATASET:
        images = store.reject_dataset(sub["username"], sub["species"])
        db.review_submission(sid, SUBMISSION_REJECTED, reviewer)
        return {"id": sid, "kind": KIND_DATASET, "images": images}
    if sub["kind"] == KIND_MODEL:
        store.delete("models", sub["path"])                        # toglie anche il .json e le cartelle vuote
        db.review_submission(sid, SUBMISSION_REJECTED, reviewer)
        return {"id": sid, "kind": KIND_MODEL, "path": sub["path"]}
    photos = store.reject_media(sub["username"], sub["species"], sub["kind"])   # deletes the files
    db.review_submission(sid, SUBMISSION_REJECTED, reviewer)         # ma la riga resta, con lo stato "rejected"
    return {"id": sid, "kind": sub["kind"], "species": sub["species"], "photos": photos}

def catalog(db: Database, kind: str, store: Optional[Storage] = None) -> List[Dict[str, Any]]:
    """The approved items of a kind, for the catalogs: alphabetical by species, then by date.
    Only the date is given, never the time (privacy of the users). Datasets also say which species they contain."""
    rows = db.list_submissions(status=SUBMISSION_APPROVED, kind=kind)
    items = [{"kind": kind, "species": r["species"], "uploader": r["username"], "approved_by": r["reviewed_by"],
              "date": datetime.fromtimestamp(r["created"]).date().isoformat(), "path": r["path"],
              "items": r["photos"]} for r in rows]
    if kind == KIND_DATASET and store is not None:
        for i in items:
            i["classes"] = store.dataset_classes(i["path"])
    return sorted(items, key=lambda i: (i["species"].lower(), i["date"], i["path"]))