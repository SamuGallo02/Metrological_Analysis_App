"""
Module for Persisting the Stereo Camera Calibration
=====================================================================
Saves/loads to a JSON file the StereoConfig parameters (baseline, focal length)
set by the user in the GUI, so they are kept between one session
and the next of the app instead of reverting to default values at every restart.

Autore: Samuele Gallo
"""

from __future__ import annotations

import json
from pathlib import Path

from corpse.functions.analysis.analysis import StereoConfig

CALIBRATION_FILE = Path("stereo_calibration.json")


def load_calibration(path: Path = CALIBRATION_FILE) -> StereoConfig:
    """Loads the saved calibration. Returns the default values if the file does not exist or is corrupted."""
    default = StereoConfig()
    if not path.is_file():
        return default

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        return StereoConfig(
            baseline_mm=float(data.get("baseline_mm", default.baseline_mm)),
            focal_length_px=float(data.get("focal_length_px", default.focal_length_px)),
        )
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return default


def save_calibration(config: StereoConfig, path: Path = CALIBRATION_FILE) -> None:
    """Saves the current calibration to file."""
    data = {
        "baseline_mm": config.baseline_mm,
        "focal_length_px": config.focal_length_px,
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)