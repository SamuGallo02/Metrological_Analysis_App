"""
Thread di addestramento YOLO: esegue model.train() fuori dal thread
dell'interfaccia, cosi' la finestra resta reattiva. Comunica con la pagina
solo tramite segnali Qt (log, fine, errore).

Autore: Samuele Gallo
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from training.config import MODELS_DIR, RUN_NAME, RUNS_DIR


class TrainingWorker(QThread):
    """Thread secondario che esegue l'addestramento YOLO senza bloccare la GUI."""
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

            best_model_path = Path(results.save_dir) / "weights" / "best.pt"
            if best_model_path.exists():
                MODELS_DIR.mkdir(parents=True, exist_ok=True)
                # .name: se il modello base e' passato come percorso completo
                # (es. models/yolo11n-seg.pt) va tenuto solo il nome del file,
                # altrimenti il nome di destinazione conterrebbe un percorso.
                dest_path = MODELS_DIR / f"trained_{Path(self.base_model).name}"
                shutil.copy2(best_model_path, dest_path)
                self.finished_signal.emit(str(dest_path))
            else:
                self.error_signal.emit("Training terminato ma non è stato trovato il file dei pesi salvato.")

        except Exception as exc:
            self.error_signal.emit(str(exc))
