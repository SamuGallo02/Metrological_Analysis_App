"""Running a YOLO training, without any interface.

Used by the training page (inside its thread) and by the worker that takes the jobs the server queues, so the two
follow exactly the same steps and produce the same files.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from common.model_metadata import metrics_from_results, model_filename

from .config import MODELS_DIR, RUN_NAME, RUNS_DIR

Log = Optional[Callable[[str], None]]


def train_model(data_yaml: str, base_model: str, epochs: int, imgsz: int, batch: int, device: str,
                log: Log = None, models_dir: Optional[Path] = None) -> Tuple[Path, Dict[str, float]]:
    """Trains and returns (file of the trained model, measurements). Raises an exception if it does not finish."""
    say = log or (lambda _line: None)
    from ultralytics import YOLO                       # imported here: the server and the tests do without it

    say(f"Caricamento modello base: {base_model}...")
    model = YOLO(base_model)
    say(f"Avvio addestramento su device '{device}' per {epochs} epoche...")
    results = model.train(data=data_yaml, epochs=epochs, imgsz=imgsz, batch=batch, device=device,
                          project=str(RUNS_DIR), name=RUN_NAME, exist_ok=True)
    metrics = metrics_from_results(results)
    best = Path(results.save_dir) / "weights" / "best.pt"
    if not best.exists():
        raise RuntimeError("Training terminato ma non è stato trovato il file dei pesi salvato.")
    folder = Path(models_dir or MODELS_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / model_filename(Path(data_yaml).parent.name, base_model)
    shutil.copy2(best, dest)
    return dest, metrics
