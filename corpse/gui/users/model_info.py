"""Le righe di testo che descrivono un modello a partire dai suoi metadati (senza Qt: si prova come una funzione)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from common.i18n import tr

# (chiave nei metadati, nome mostrato): sono termini tecnici, uguali in tutte le lingue
_METRICS = (("mAP50", "mAP50"), ("mAP50_95", "mAP50-95"), ("precision", "precision"), ("recall", "recall"))


def _dict(value: Any) -> Dict[str, Any]:
    """I metadati arrivano da un file: un campo che non è un dizionario conta come assente."""
    return value if isinstance(value, dict) else {}


def model_info_lines(meta: Optional[Dict[str, Any]]) -> List[str]:
    """Le righe da mostrare per un modello; ogni riga compare solo se il dato c'è."""
    meta = _dict(meta)
    lines: List[str] = []
    if meta.get("species"):
        lines.append(tr("Species: {species}", species=meta["species"]))
    if meta.get("created"):
        lines.append(tr("Created: {date}", date=str(meta["created"])[:10]))          # solo la data
    if meta.get("trained_by"):
        lines.append(tr("Trained by: {user}", user=meta["trained_by"]))
    if meta.get("base_model"):
        lines.append(tr("Base model: {model}", model=meta["base_model"]))

    dataset = _dict(meta.get("dataset"))
    if dataset.get("name"):
        if dataset.get("images") is not None:
            lines.append(tr("Dataset: {name} ({n} images)", name=dataset["name"], n=dataset["images"]))
        else:
            lines.append(tr("Dataset: {name}", name=dataset["name"]))

    p = _dict(meta.get("parameters"))
    if all(k in p for k in ("epochs", "imgsz", "batch")):
        lines.append(tr("Training: {epochs} epochs, image size {imgsz}, batch {batch}, {device}",
                        epochs=p["epochs"], imgsz=p["imgsz"], batch=p["batch"], device=meta.get("device", "")))

    metrics = _dict(meta.get("metrics"))
    shown = [f"{label} {metrics[key]:.2f}" for key, label in _METRICS
             if isinstance(metrics.get(key), (int, float)) and not isinstance(metrics.get(key), bool)]
    if shown:
        lines.append(tr("Metrics: {values}", values=", ".join(shown)))

    return lines or [tr("No details available for this model.")]