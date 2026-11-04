"""
YOLO training thread: runs model.train() outside the interface thread,
so the window stays responsive. It communicates with the page
only through Qt signals (log, finished, error).

Autore: Samuele Gallo
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from corpse.functions.training.config import MODELS_DIR, RUN_NAME, RUNS_DIR

from typing import Dict

from common.model_metadata import metrics_from_results, model_filename


class TrainingWorker(QThread):
    """Background thread that runs YOLO training without blocking the GUI."""
    log_signal = Signal(str)
    finished_signal = Signal(str)
    error_signal = Signal(str)

    def __init__(self, data_yaml: str, base_model: str, epochs: int, imgsz: int, batch: int, device: str) -> None:
        super().__init__()
        self.data_yaml = data_yaml
        self.base_model = base_model
        self.epochs = epochs
        self.imgsz = imgsz
        self.batch = batch
        self.device = device
        self.metrics: Dict[str, float] = {}          # le misure del training, disponibili a lavoro finito

    def run(self) -> None:
        try:
            from ultralytics import YOLO

            self.log_signal.emit(f"Caricamento modello base: {self.base_model}...")
            model = YOLO(self.base_model)

            self.log_signal.emit(f"Avvio addestramento su device '{self.device}' per {self.epochs} epoche...")
            results = model.train(
                data=self.data_yaml,
                epochs=self.epochs,
                imgsz=self.imgsz,
                batch=self.batch,
                device=self.device,
                project=str(RUNS_DIR),
                name=RUN_NAME,
                exist_ok=True,
            )

            self.metrics = metrics_from_results(results)

            best_model_path = Path(results.save_dir) / "weights" / "best.pt"
            if best_model_path.exists():
                MODELS_DIR.mkdir(parents=True, exist_ok=True)
                dataset = Path(self.data_yaml).parent.name
                dest_path = MODELS_DIR / model_filename(dataset, self.base_model)
                shutil.copy2(best_model_path, dest_path)
                self.finished_signal.emit(str(dest_path))
            else:
                self.error_signal.emit("Training terminato ma non è stato trovato il file dei pesi salvato.")

        except Exception as exc:
            self.error_signal.emit(str(exc))
