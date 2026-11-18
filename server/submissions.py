"""Registrazione di un invio di foto di specie, dopo la fine del caricamento.

Autore: Samuele Gallo
"""
from __future__ import annotations
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

from common.errors import AppError
from common.params import VIS_PUBLIC

from .db import Database
from .params import (SPECIES_RE, PENDING, SUBMISSION_APPROVED, SUBMISSION_PENDING, SUBMISSION_REJECTED, KIND_PHOTOS,
                     KIND_DATASET, KIND_MODEL, KINDS_MEDIA)
from .media_tree import count_media, validate_media_dir
from .storage import Storage
from .dataset_tree import count_dataset_images, validate_dataset_dir


def submit_species(store: Storage, db: Database, username: str, species: str, kind: str = KIND_PHOTOS,
                   admin: bool = False, group: str = "", visibility: str = VIS_PUBLIC,
                   vis_group: str = "") -> Dict[str, Any]:
    """Registers the photos / stereo photos / videos a user uploaded for a species. What an administrator
    sends is approved at once, by the administrator. With `group`, the upload is published on behalf of a work
    group: the group is then the author, in the catalog and in the name of the folder."""
    if kind not in KINDS_MEDIA:
        raise AppError("Unknown kind of upload.", 422)
    folder = store.pending_media_dir(username, species, kind)       # 404 if there is nothing waiting
    errors = validate_media_dir(folder, kind)
    if errors:
        raise errors[0]                                            # refused: no row is created
    path = f"{PENDING}/{username}/{species}"
    _check_not_waiting(db, username, path, kind)
    items = count_media(folder, kind)
    sid = db.add_submission(username, species, path, items, kind=kind, group=group, visibility=visibility,
                            vis_group=vis_group)
    result = {"id": sid, "kind": kind, "group": group, "species": species, "path": path, "photos": items,
              "visibility": visibility, "pending": not admin}
    if admin:
        approve_submission(store, db, sid, username)
        result["pending"] = False
    return result

def _check_not_waiting(db: Database, username: str, path: str, kind: Optional[str] = None) -> None:
    for s in db.list_submissions(username=username, status=SUBMISSION_PENDING):
        if s["path"] == path and (kind is None or s["kind"] == kind):
            raise AppError("You already have a pending submission for this item.", 409)


def _record(db: Database, username: str, subject: str, path: str, items: int, kind: str, admin: bool,
            group: str = "", visibility: str = VIS_PUBLIC, vis_group: str = "") -> int:
    """Registers the submission. What an administrator publishes is approved at once, by the administrator."""
    _check_not_waiting(db, username, path, kind)
    sid = db.add_submission(username, subject, path, items, kind=kind, group=group, visibility=visibility,
                            vis_group=vis_group)
    if admin:
        db.review_submission(sid, SUBMISSION_APPROVED, username)
    return sid


def submit_dataset(store: Storage, db: Database, username: str, name: str, admin: bool = False,
                   group: str = "", visibility: str = VIS_PUBLIC, vis_group: str = "") -> Dict[str, Any]:
    folder = store.pending_dataset_dir(username, name, admin)      # 404 se non c'è nulla da inviare
    errors = validate_dataset_dir(folder)
    if errors:
        raise errors[0]                                            # refused: no row is created
    path = name if admin else f"{PENDING}/{username}/{name}"
    images = count_dataset_images(folder)
    sid = _record(db, username, name, path, images, KIND_DATASET, admin, group, visibility, vis_group)
    return {"id": sid, "kind": KIND_DATASET, "name": name, "group": group, "path": path, "images": images,
            "visibility": visibility, "pending": not admin}


def submit_model(store: Storage, db: Database, username: str, species: str, file: str, admin: bool = False,
                 group: str = "", visibility: str = VIS_PUBLIC, vis_group: str = "") -> Dict[str, Any]:
    path = store.pending_model_path(username, species, file, admin)   # 404 if the file was not uploaded
    sid = _record(db, username, species, path, 1, KIND_MODEL, admin, group, visibility, vis_group)
    return {"id": sid, "kind": KIND_MODEL, "species": species, "file": file, "path": path, "group": group,
            "visibility": visibility, "pending": not admin}


def author_of(sub: Dict[str, Any]) -> str:
    """Who signs an upload: the work group it was published for, or the person who sent it."""
    return sub["group_name"] or sub["username"] if "group_name" in sub.keys() else sub["username"]



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
    return f"{base}/{base}_{author_of(sub)}_{day}"

def approve_submission(store: Storage, db: Database, sid: int, reviewer: str) -> Dict[str, Any]:
    sub = _pending_submission(db, sid)
    if sub["kind"] == KIND_DATASET:
        name, images = store.approve_dataset(sub["username"], sub["species"], _dataset_final_name(store, sub))
        db.review_submission(sid, SUBMISSION_APPROVED, reviewer, path=name, photos=images)
        return {"id": sid, "kind": KIND_DATASET, "name": name, "images": images}
    if sub["kind"] == KIND_MODEL:
        final = store.approve_model(sub["path"])                   # the model and its .json move together
        db.review_submission(sid, SUBMISSION_APPROVED, reviewer, path=final)
        return {"id": sid, "kind": KIND_MODEL, "path": final}
    day = datetime.fromtimestamp(sub["created"]).date()              # the date of the upload
    folder, photos = store.approve_media(sub["username"], sub["species"], sub["kind"], day, author_of(sub))
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
        store.delete("models", sub["path"])                        # removes the .json and the empty folders too
        db.review_submission(sid, SUBMISSION_REJECTED, reviewer)
        return {"id": sid, "kind": KIND_MODEL, "path": sub["path"]}
    photos = store.reject_media(sub["username"], sub["species"], sub["kind"])   # deletes the files
    db.review_submission(sid, SUBMISSION_REJECTED, reviewer)         # ma la riga resta, con lo stato "rejected"
    return {"id": sid, "kind": sub["kind"], "species": sub["species"], "photos": photos}

def catalog(db: Database, kind: str, store: Optional[Storage] = None) -> List[Dict[str, Any]]:
    """The approved items of a kind, for the catalogs: alphabetical by species, then by date.
    Only the date is given, never the time (privacy of the users). Datasets also say which species they contain."""
    rows = db.list_submissions(status=SUBMISSION_APPROVED, kind=kind)
    items = [{"id": r["id"], "kind": kind, "species": r["species"], "uploader": author_of(r), "sent_by": r["username"],
              "group": r["group_name"], "approved_by": r["reviewed_by"],
              "date": datetime.fromtimestamp(r["created"]).date().isoformat(), "path": r["path"],
              "items": r["photos"], "visibility": r["visibility"],
              "vis_group": r["vis_group"] if "vis_group" in r.keys() else ""} for r in rows]
    if kind == KIND_DATASET and store is not None:
        for i in items:
            i["classes"] = store.dataset_classes(i["path"])
    return sorted(items, key=lambda i: (i["species"].lower(), i["date"], i["path"]))