"""Where a file dialog opens.

Two different needs, and the wrong one is what makes a program tiring to use:

  - choosing something of one's own to bring in (photos, a folder of a dive, a model) starts on the **Desktop**,
    where people leave what they are working with;
  - choosing something the application already manages (a dataset, a trained model, where a download goes)
    starts in **that folder of the application**, so nobody has to walk the disk to find it.

Autore: Samuele Gallo
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from common.paths import MODELS_DIR, PHOTO_DIR, STEREO_PHOTO_DIR, STEREO_VIDEO_DIR, TRAINING_DIR, VIDEO_DIR

MANAGED = {"photo": PHOTO_DIR, "photo_stereo": STEREO_PHOTO_DIR, "video": VIDEO_DIR,
           "video_stereo": STEREO_VIDEO_DIR, "datasets": TRAINING_DIR, "models": MODELS_DIR}


def desktop() -> str:
    """The Desktop of this user, whatever it is called on this system; the home folder when there is none."""
    home = Path.home()
    for name in (os.environ.get("XDG_DESKTOP_DIR", ""), "Desktop", "Scrivania", "Bureau", "Escritorio",
                 "Schreibtisch"):
        if not name:
            continue
        candidate = Path(name) if os.path.isabs(name) else home / name
        if candidate.is_dir():
            return str(candidate)
    one_drive = os.environ.get("OneDrive") or ""              # on Windows the Desktop often lives there
    if one_drive and (Path(one_drive) / "Desktop").is_dir():
        return str(Path(one_drive) / "Desktop")
    return str(home)


def managed(kind: str, fallback: Optional[Path] = None) -> str:
    """The folder of the application for a kind of file ("photo", "models", "datasets"...), made if missing."""
    folder = MANAGED.get(kind, fallback)
    if folder is None:
        return desktop()
    try:
        Path(folder).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return str(folder)


def inside(folder: Optional[Path], fallback: str = "") -> str:
    """A folder that already exists (the one the user is looking at), or `fallback`, or the Desktop."""
    if folder is not None and Path(folder).is_dir():
        return str(folder)
    return fallback or desktop()
