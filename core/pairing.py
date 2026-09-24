"""
Modulo per la Gestione e l'Accoppiamento di Immagini e Video Stereo
====================================================================
Fornisce le funzioni e le strutture dati per la scansione delle cartelle
di acquisizione, l'accoppiamento temporale (Pairing) dei fotogrammi/video
stereo (Camera Destra / Camera Sinistra) e il controllo d'integrita' dei
dataset — incluso il rifiuto di formati di cartella pensati per un'altra
pagina (es. una cartella rx/lx usata per errore nell'Analisi Foto).

Formato atteso per le COPPIE STEREO (foto o video): sottocartelle "rx/" e
"lx/" (o "right/"/"left/") dentro la cartella scelta — esattamente come
genera il demone Sensing-Rigs su Raspberry Pi (vedi constants.c:
DAEMON_PATH_CAP="captures/", DAEMON_PATH_RX="rx/", DAEMON_PATH_LX="lx/").
Per le foto, i file dentro rx/lx sono nominati col solo timestamp Unix
epoch (es. "1723130400.jpg"); per i video, ciascuna sottocartella contiene
un solo file video.

Autore: Samuele Gallo
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}

# Manteniamo il nome storico usato altrove nel codice.
VALID_EXTENSIONS = IMAGE_EXTENSIONS

_RIGHT_DIR_NAMES = ("rx", "right", "r")
_LEFT_DIR_NAMES = ("lx", "left", "l")


def is_stereo_dataset_folder(folder: Path) -> bool:
    """
    True se la cartella e' nel formato "coppia stereo" (contiene ENTRAMBE le
    sottocartelle rx/lx o right/left) — a prescindere dal fatto che dentro ci
    siano foto o un video. Usata per impedire che lo stesso formato di
    cartella venga usato per errore in una pagina diversa (l'Analisi Foto
    vuole cartelle FLAT di immagini, non rx/lx).
    """
    folder = Path(folder)
    if not folder.is_dir():
        return False
    names = {p.name.lower() for p in folder.iterdir() if p.is_dir()}
    return bool(names & set(_RIGHT_DIR_NAMES)) and bool(names & set(_LEFT_DIR_NAMES))


def _find_side_dirs(target_directory: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """Cerca sottocartelle rx/lx (o right/left) dentro target_directory."""
    right_dir = next(
        (p for p in target_directory.iterdir() if p.is_dir() and p.name.lower() in _RIGHT_DIR_NAMES),
        None,
    )
    left_dir = next(
        (p for p in target_directory.iterdir() if p.is_dir() and p.name.lower() in _LEFT_DIR_NAMES),
        None,
    )
    if right_dir is not None and left_dir is not None:
        return right_dir, left_dir
    return None, None


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
    Usata SOLO dall'Analisi Stereo (foto): rifiuta esplicitamente una
    cartella che non sia nel formato rx/lx, cosi' non si puo' scegliere per
    errore una cartella pensata per l'Analisi Foto.
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

        right_dir, left_dir = _find_side_dirs(self.target_directory)
        if right_dir is None or left_dir is None:
            raise FileNotFoundError(
                f"Sottocartelle rx/lx (o right/left) non trovate in: {self.target_directory}\n"
                f"Questa cartella non e' nel formato atteso dall'Analisi Stereo."
            )

        return self._pair_from_side_dirs(right_dir, left_dir)

    @staticmethod
    def _pair_from_side_dirs(right_dir: Path, left_dir: Path) -> List[StereoPair]:
        """Accoppia i file di due sottocartelle in base al nome (stem) condiviso."""

        def _index(directory: Path) -> Dict[str, Path]:
            return {
                f.stem: f
                for f in directory.iterdir()
                if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
            }

        right_images = _index(right_dir)
        left_images = _index(left_dir)

        common_timestamps = sorted(set(right_images.keys()) & set(left_images.keys()))

        return [
            StereoPair(timestamp=ts, right_path=right_images[ts], left_path=left_images[ts])
            for ts in common_timestamps
        ]


@dataclass(frozen=True)
class SingleImageItem:
    """Una singola immagine di una sequenza (cartella Analisi Foto), col suo nome/timestamp."""
    timestamp: str
    image_path: Path


class SingleImageFinder:
    """
    Scansiona una cartella FLAT di immagini (nessuna sottocartella rx/lx) e le
    ordina per nome file, trattandole come una sequenza — come i fotogrammi
    di un video, ma gia' su disco. Usata dall'Analisi Foto (modalita' Singola).
    Rifiuta esplicitamente una cartella in formato rx/lx: quel formato e'
    riservato all'Analisi Stereo, non va riusato qui per errore.
    """

    def __init__(self, target_directory: Path) -> None:
        self.target_directory = Path(target_directory)

    def scan(self) -> List[SingleImageItem]:
        if not self.target_directory.is_dir():
            raise FileNotFoundError(f"La directory specificata non esiste: {self.target_directory}")

        if is_stereo_dataset_folder(self.target_directory):
            raise ValueError(
                f"'{self.target_directory.name}' e' una cartella in formato stereo (contiene rx/lx): "
                f"usala nella pagina Analisi Stereo, non qui."
            )

        files = sorted(
            (f for f in self.target_directory.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS),
            key=lambda f: f.stem,
        )
        return [SingleImageItem(timestamp=f.stem, image_path=f) for f in files]


def find_single_video(target_directory: Path) -> Path:
    """
    Cerca UN SOLO file video direttamente dentro target_directory (Analisi
    Video, modalita' Singolo). Rifiuta una cartella in formato stereo
    (rx/lx): quel formato e' per la modalita' Video Stereo, non per questa.
    """
    target_directory = Path(target_directory)
    if not target_directory.is_dir():
        raise FileNotFoundError(f"La directory specificata non esiste: {target_directory}")

    if is_stereo_dataset_folder(target_directory):
        raise ValueError(
            f"'{target_directory.name}' e' una cartella in formato stereo (contiene rx/lx): "
            f"usala nella modalita' Video Stereo, non qui."
        )

    videos = sorted(
        f for f in target_directory.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS
    )
    if not videos:
        raise FileNotFoundError(f"Nessun file video trovato in: {target_directory}")

    return videos[0]


@dataclass(frozen=True)
class StereoVideoPair:
    """Rappresenta la coppia di file video sincronizzati (destro/sinistro) di un dataset stereo."""
    right_video: Path
    left_video: Path


def find_stereo_video_pair(target_directory: Path) -> StereoVideoPair:
    """
    Cerca una coppia di video sincronizzati nelle sottocartelle rx/lx di
    target_directory (Analisi Video, modalita' Stereo) — un solo file video
    per sottocartella. Rifiuta esplicitamente una cartella che NON sia nel
    formato rx/lx (quella e' la modalita' Video Singolo).
    """
    target_directory = Path(target_directory)
    if not target_directory.is_dir():
        raise FileNotFoundError(f"La directory specificata non esiste: {target_directory}")

    right_dir, left_dir = _find_side_dirs(target_directory)
    if right_dir is None or left_dir is None:
        raise FileNotFoundError(
            f"Sottocartelle rx/lx (o right/left) non trovate in: {target_directory}\n"
            f"La modalita' Video Stereo richiede due video sincronizzati in rx/ e lx/."
        )

    def _first_video(directory: Path) -> Path:
        videos = sorted(f for f in directory.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS)
        if not videos:
            raise FileNotFoundError(f"Nessun file video trovato in: {directory}")
        return videos[0]

    return StereoVideoPair(right_video=_first_video(right_dir), left_video=_first_video(left_dir))
