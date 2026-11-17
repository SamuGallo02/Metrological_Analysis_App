"""
YOLO training thread: runs model.train() outside the interface thread,
so the window stays responsive. It communicates with the page
only through Qt signals (log, finished, error).

Autore: Samuele Gallo
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from corpse.functions.training.run import train_model

from typing import Dict



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
            path, self.metrics = train_model(self.data_yaml, self.base_model, self.epochs, self.imgsz, self.batch,
                                             self.device, log=self.log_signal.emit)
            self.finished_signal.emit(str(path))
        except Exception as exc:
            self.error_signal.emit(str(exc))
