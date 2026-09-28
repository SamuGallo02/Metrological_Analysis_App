"""
Modulo di utilità per l'individuazione delle webcam disponibili sul sistema
(integrata del portatile e/o USB esterne, incluso un eventuale sensing-rig
stereo con due camere sincronizzate). Condiviso dalla demo webcam a riga di
comando (tools/webcam_demo.py) e dalla finestra di configurazione della demo
nella GUI (gui/home_gui.py), cosi' l'elenco delle camere individuate e'
sempre lo stesso in entrambi i punti.

Autore: Samuele Gallo
"""

from __future__ import annotations

import sys
from typing import List

import cv2


def _capture_backend() -> int:
    """Su Windows forza il backend DirectShow: piu' affidabile di quello di
    default per aprire correttamente sia la camera integrata sia le USB
    esterne con la risoluzione richiesta (il backend di default ha causato,
    su alcune macchine, un'apertura riuscita ma con fotogrammi neri)."""
    return cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY


def open_camera(index: int, width: int = 1280, height: int = 720, warmup_frames: int = 5):
    """
    Apre la camera all'indice richiesto, imposta la risoluzione desiderata e
    scarta i primi `warmup_frames` fotogrammi: molte webcam restituiscono
    fotogrammi neri o non ancora esposti correttamente per i primi istanti
    dopo l'apertura, soprattutto subito dopo aver cambiato risoluzione.
    Ritorna il cv2.VideoCapture aperto, oppure None se la camera non risponde.
    """
    cap = cv2.VideoCapture(index, _capture_backend())
    if not cap.isOpened():
        cap.release()
        return None

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    ok = False
    for _ in range(warmup_frames):
        ok, _ = cap.read()

    if not ok:
        cap.release()
        return None

    return cap


def list_available_cameras(max_index: int = 6) -> List[int]:
    """Prova ad aprire le prime `max_index` camere (indici 0..max_index-1) e
    ritorna gli indici di quelle che rispondono con un fotogramma valido."""
    found: List[int] = []
    for idx in range(max_index):
        cap = open_camera(idx, warmup_frames=1)  # solo 1 frame: qui serve solo sapere se risponde
        if cap is not None:
            found.append(idx)
            cap.release()
    return found
