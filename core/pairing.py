"""
Modulo per la Gestione e l'Accoppiamento di Immagini Stereo
===========================================================
Fornisce le funzioni e le strutture dati per la scansione delle cartelle
di acquisizione, l'accoppiamento temporale (Pairing) dei fotogrammi stereo
(Camera Destra / Camera Sinistra) e il controllo d'integrità dei dataset.

Formato atteso: sottocartelle "rx/" e "lx/" (o "right/"/"left/") dentro la
cartella scelta, ciascuna con i file nominati con il solo timestamp Unix
epoch (es. "1723130400.jpg") — esattamente come genera il demone
Sensing-Rigs su Raspberry Pi (vedi constants.c: DAEMON_PATH_CAP="captures/",
DAEMON_PATH_RX="rx/", DAEMON_PATH_LX="lx/").
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}

_RIGHT_DIR_NAMES = ("rx", "right", "r")
_LEFT_DIR_NAMES = ("lx", "left", "l")


@dataclass(frozen=True)
class StereoPair:
    """Rappresenta una coppia di immagini stereo correlate dal medesimo timestamp."""
    timestamp: str
    right_path: Path
    left_path: Path


class StereoPairFinder:
    """
    Classe per l'identificazione e l'accoppiamento delle immagini stereo
    presenti nelle sottocartelle rx/lx di una cartella di acquisizione.
    """

    def __init__(self, target_directory: Path) -> None:
        self.target_directory = Path(target_directory)

    def scan_and_pair(self) -> List[StereoPair]:
        """
        Scansiona la directory specificata, individua le sottocartelle rx/lx,
        e restituisce la lista delle coppie con timestamp corrispondente in entrambe.
        """
        if not self.target_directory.is_dir():
            raise FileNotFoundError(f"La directory specificata non esiste: {self.target_directory}")

        right_dir, left_dir = self._find_side_dirs()
        if right_dir is None or left_dir is None:
            raise FileNotFoundError(
                f"Sottocartelle rx/lx (o right/left) non trovate in: {self.target_directory}"
            )

        return self._pair_from_side_dirs(right_dir, left_dir)

    def _find_side_dirs(self) -> Tuple[Optional[Path], Optional[Path]]:
        """Cerca sottocartelle rx/lx (o right/left) dentro target_directory."""
        right_dir = next(
            (p for p in self.target_directory.iterdir() if p.is_dir() and p.name.lower() in _RIGHT_DIR_NAMES),
            None,
        )
        left_dir = next(
            (p for p in self.target_directory.iterdir() if p.is_dir() and p.name.lower() in _LEFT_DIR_NAMES),
            None,
        )
        if right_dir is not None and left_dir is not None:
            return right_dir, left_dir
        return None, None

    def _pair_from_side_dirs(self, right_dir: Path, left_dir: Path) -> List[StereoPair]:
        """Accoppia i file di due sottocartelle in base al nome (stem) condiviso."""

        def _index(directory: Path) -> Dict[str, Path]:
            return {
                f.stem: f
                for f in directory.iterdir()
                if f.is_file() and f.suffix.lower() in VALID_EXTENSIONS
            }

        right_images = _index(right_dir)
        left_images = _index(left_dir)

        common_timestamps = sorted(set(right_images.keys()) & set(left_images.keys()))

        return [
            StereoPair(timestamp=ts, right_path=right_images[ts], left_path=left_images[ts])
            for ts in common_timestamps
        ]