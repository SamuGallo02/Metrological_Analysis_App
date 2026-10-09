"""Operating system user folders."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from ..params import DATA_DIR_NAME, LOCAL_DATA_PARTS, LOCAL_FOLDER_NAMES, VENV_PARENT


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


# ---- project folders (anchored to this file, not to the folder Python is launched from) ----------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_DIR = PROJECT_ROOT.joinpath(*LOCAL_DATA_PARTS)
PHOTO_DIR = LOCAL_DIR / LOCAL_FOLDER_NAMES["photo"]
STEREO_PHOTO_DIR = LOCAL_DIR / LOCAL_FOLDER_NAMES["photo_stereo"]
VIDEO_DIR = LOCAL_DIR / LOCAL_FOLDER_NAMES["video"]
STEREO_VIDEO_DIR = LOCAL_DIR / LOCAL_FOLDER_NAMES["video_stereo"]
TRAINING_DIR = LOCAL_DIR / LOCAL_FOLDER_NAMES["training"]
MODELS_DIR = LOCAL_DIR / LOCAL_FOLDER_NAMES["models"]
RESULTS_DIR = LOCAL_DIR / LOCAL_FOLDER_NAMES["results"]
RUNS_DIR = LOCAL_DIR / LOCAL_FOLDER_NAMES["runs"] / "train"
VENV_PARENT_DIR = PROJECT_ROOT / VENV_PARENT
CLASSES_FILE = PROJECT_ROOT / "common" / "config" / "object_classes.json"
ICON_FILE = PROJECT_ROOT / "common" / "assets" / "app_icon.ico"
