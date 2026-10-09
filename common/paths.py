"""Cartelle dell'utente del sistema operativo."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .params import DATA_DIR_NAME


def user_data_dir() -> Path:
    override = os.environ.get("AM_USER_DIR")
    if override:
        return Path(override)
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / DATA_DIR_NAME
