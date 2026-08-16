"""
Modulo per la Persistenza della Calibrazione della Fotocamera Stereo
=====================================================================
Salva/carica su file JSON i parametri di StereoConfig (baseline, focale,
mm/px a 1m) impostati dall'utente nella GUI, cosi' restano memorizzati tra
una sessione e l'altra dell'app invece di tornare ai valori di default ad
ogni riavvio.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.analysis import StereoConfig

CALIBRATION_FILE = Path("stereo_calibration.json")


def load_calibration(path: Path = CALIBRATION_FILE) -> StereoConfig:
    """Carica la calibrazione salvata. Ritorna i valori di default se il file non esiste o e' corrotto."""
    default = StereoConfig()
    if not path.is_file():
        return default

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        mm_per_px = data.get("mm_per_px_at_1m")
        return StereoConfig(
            baseline_mm=float(data.get("baseline_mm", default.baseline_mm)),
            focal_length_px=float(data.get("focal_length_px", default.focal_length_px)),
            mm_per_px_at_1m=float(mm_per_px) if mm_per_px else None,
        )
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return default


def save_calibration(config: StereoConfig, path: Path = CALIBRATION_FILE) -> None:
    """Salva la calibrazione corrente su file."""
    data = {
        "baseline_mm": config.baseline_mm,
        "focal_length_px": config.focal_length_px,
        "mm_per_px_at_1m": config.mm_per_px_at_1m,
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
