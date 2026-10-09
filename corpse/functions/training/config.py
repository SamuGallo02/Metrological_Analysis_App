"""
Constants and paths of the Training module. Everything that is "configuration"
(folders, suggested base models, default parameter values) lives here,
so changing it requires touching neither the logic nor the interface.

Paths are anchored to the project folder (not to the folder from which
Python is launched), so the module works the same way both
from the main app and on its own (python -m training).

Autore: Samuele Gallo
"""

from __future__ import annotations

from pathlib import Path

from common.paths import MODELS_DIR, PROJECT_ROOT, RUNS_DIR, TRAINING_DIR as TDATASET_DIR  # noqa: F401

RUN_NAME = "custom_yolo_model"

BASE_MODEL_OPTIONS = [
    "yolo11n-seg.pt", "yolo11s-seg.pt", "yolo11m-seg.pt", "yolo11l-seg.pt",
    "yolov8n-seg.pt", "yolov8s-seg.pt", "yolov8m-seg.pt", "yolov8l-seg.pt",
    "yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolo11l.pt",
]

DEFAULT_EPOCHS = 50
DEFAULT_IMGSZ = 640
DEFAULT_BATCH = 8

COLAB_URL = "https://colab.research.google.com/#create=true"
