"""
Utility module for detecting the webcams available on the system
(the laptop's built-in one and/or external USB ones, including a possible stereo
sensing rig with two synchronized cameras). Shared by the command-line webcam
demo (tools/webcam_demo.py) and by the demo configuration window
in the GUI (gui/home_gui.py), so the list of detected cameras is
always the same in both places.

Autore: Samuele Gallo
"""

from __future__ import annotations

import sys
from typing import List

import cv2


def _capture_backend() -> int:
    """On Windows, forces the DirectShow backend: more reliable than the default
    one for correctly opening both the built-in camera and external USB ones
    at the requested resolution (the default backend has caused, on some
    machines, a successful open but with black frames)."""
    return cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY


def open_camera(index: int, width: int = 1280, height: int = 720, warmup_frames: int = 5):
    """
    Opens the camera at the requested index, sets the desired resolution and
    discards the first `warmup_frames` frames: many webcams return
    black or not yet properly exposed frames for the first moments
    after opening, especially right after changing resolution.
    Returns the opened cv2.VideoCapture, or None if the camera does not respond.
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
    """Tries to open the first `max_index` cameras (indices 0..max_index-1) and
    returns the indices of those that respond with a valid frame."""
    found: List[int] = []
    for idx in range(max_index):
        cap = open_camera(idx, warmup_frames=1)  # only 1 frame: here we only need to know whether it responds
        if cap is not None:
            found.append(idx)
            cap.release()
    return found
