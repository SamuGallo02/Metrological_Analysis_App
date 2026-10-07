"""
Costanti e percorsi del modulo Training. Tutto cio' che e' "configurazione"
(cartelle, modelli base proposti, valori di default dei parametri) sta qui,
cosi' per cambiarlo non serve toccare la logica ne' l'interfaccia.

I percorsi sono ancorati alla cartella del progetto (non alla cartella da cui
viene lanciato Python), quindi il modulo funziona allo stesso modo sia
dall'app principale sia da solo (python -m training).

Autore: Samuele Gallo
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

MODELS_DIR = PROJECT_ROOT / "models"
TDATASET_DIR = PROJECT_ROOT / "Dataset_Training"
RUNS_DIR = PROJECT_ROOT / "runs" / "train"
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
