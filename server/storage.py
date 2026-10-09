"""Cartelle del server con percorsi sicuri.

Aree comuni (photos, models, datasets):
  * "user"   : legge e scarica ovunque (tranne la quarantena dei modelli), CREA nuovi file e cartelle ma non
               sovrascrive, rinomina, sposta o elimina nulla.
  * "server" : tutto, inclusa l'approvazione dei modelli caricati dagli utenti.
  * Un modello .pt/.onnx caricato da un utente finisce in models/_pending/<utente>/ finche' un amministratore
    non lo approva: un .pt e' un archivio pickle e puo' eseguire codice quando viene caricato.
Area personale (mine): files/mine/<utente>/ - il proprietario legge, scrive, sposta ed elimina, entro la quota.
"""
from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

from common.errors import AppError
from common.params import AREA_MINE, AREAS, AREAS_SHARED

from .params import EXTENSIONS, MAX_BYTES, PENDING, TMP

_MAGIC = {".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",), ".png": (b"\x89PNG\r\n\x1a\n",),
          ".bmp": (b"BM",), ".webp": (b"RIFF",), ".tif": (b"II*\x00", b"MM\x00*"), ".tiff": (b"II*\x00", b"MM\x00*")}
_WIN_RESERVED = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
_lock = threading.Lock()


def clean_rel(rel: str) -> str:
    """Normalizza un percorso relativo (separatore '/'), rifiutando tutto cio' che esce dall'area."""
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


class Storage:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        for a in AREAS:
            (self.root / a).mkdir(parents=True, exist_ok=True)
        (self.root / "models" / PENDING).mkdir(exist_ok=True)

    # ---- percorsi ----------------------------------------------------------
    def base(self, area: str, owner: str) -> Path:
        if area not in AREAS:
            raise AppError("Unknown area.", 404)
        if area == AREA_MINE:
            if not owner:
                raise AppError("Unknown area.", 404)
            return self.root / AREA_MINE / owner
        return self.root / area

    def resolve(self, area: str, rel: str, admin: bool, owner: str = "") -> Tuple[Path, str]:
        rel = clean_rel(rel)
        base = self.base(area, owner)
        if area == "models" and not admin and (rel == PENDING or rel.startswith(PENDING + "/")):
            raise AppError("Area reserved to administrators.", 403)
        if area == AREA_MINE:
            base.mkdir(parents=True, exist_ok=True)
        path = (base / rel).resolve() if rel else base.resolve()
        if path != base.resolve() and base.resolve() not in path.parents:
            raise AppError("Invalid path.")
        return path, rel

    # ---- quota -------------------------------------------------------------
    def usage(self, owner: str) -> int:
        base = self.base(AREA_MINE, owner)
        if not base.exists():
            return 0
        return sum(p.stat().st_size for p in base.rglob("*") if p.is_file() and not p.is_symlink())

    # ---- lettura -----------------------------------------------------------
    def list_dir(self, area: str, rel: str, admin: bool, owner: str = "") -> Dict[str, Any]:
        path, rel = self.resolve(area, rel, admin, owner)
        if not path.is_dir():
            raise AppError("Folder not found.", 404)
        entries = []
        for p in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name.startswith(TMP) or p.is_symlink():
                continue
            if area == "models" and rel == "" and p.name == PENDING and not admin:
                continue
            st = p.stat()
            entries.append({"name": p.name, "type": "dir" if p.is_dir() else "file",
                            "size": 0 if p.is_dir() else st.st_size, "mtime": st.st_mtime})
        return {"area": area, "path": rel, "entries": entries}

    def open_file(self, area: str, rel: str, admin: bool, owner: str = "") -> Tuple[Path, int]:
        path, _ = self.resolve(area, rel, admin, owner)
        if not path.is_file() or path.is_symlink():
            raise AppError("File not found.", 404)
        return path, path.stat().st_size

    # ---- inserimento -------------------------------------------------------
    def check_new_file(self, area: str, rel: str, admin: bool, username: str, size: int,
                       quota_mb: int = 0) -> Tuple[Path, str]:
        """Valida un caricamento PRIMA di ricevere i dati; ritorna (destinazione, percorso effettivo)."""
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
        if size > MAX_BYTES[area]:
            raise AppError("File too large for this area.", 413)
        if area == "models" and not admin:
            if rel.startswith(PENDING + "/"):
                rel = rel[len(PENDING) + 1:]
            rel = f"{PENDING}/{username}/{rel}"                      # quarantena
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
        """Sposta il file ricevuto al suo posto. Nelle aree comuni l'utente non puo' sovrascrivere."""
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
        if area == "models" and not admin:
            raise AppError("Users cannot create folders in the models area.", 403)
        with _lock:
            if path.exists():
                raise AppError("Already exists.", 409)
            path.mkdir(parents=True)
        return rel

    # ---- modifica ----------------------------------------------------------
    def delete(self, area: str, rel: str, owner: str = "") -> None:
        path, rel = self.resolve(area, rel, True, owner)
        if not rel:
            raise AppError("The root of an area cannot be deleted.")
        if rel == PENDING and area == "models":
            raise AppError("The quarantine area is protected.")
        if not path.exists():
            raise AppError("Does not exist.", 404)
        shutil.rmtree(path) if path.is_dir() else path.unlink()

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
        os.replace(s, d)
        return dst

    def approve_model(self, rel: str, new_name: Optional[str] = None) -> str:
        """Sposta un modello da models/_pending/<utente>/x.pt a models/x.pt."""
        rel = clean_rel(rel)
        if not rel.startswith(PENDING + "/"):
            raise AppError("The file is not in quarantine.")
        name = clean_rel(new_name) if new_name else PurePosixPath(rel).name
        return self.move("models", rel, name)
