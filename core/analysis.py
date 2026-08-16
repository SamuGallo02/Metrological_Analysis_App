"""
Modulo di Analisi Fotogrammetrica e Segmentazione
=================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Optional, Set

import cv2
import numpy as np

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None


def select_computation_device() -> str:
    """Determina l'acceleratore hardware ottimale disponibile nel sistema."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def list_model_classes(model_path: str) -> List[str]:
    """Carica un modello YOLO e restituisce l'elenco esatto delle classi conosciute."""
    if YOLO is None:
        raise ImportError("Modulo 'ultralytics' non disponibile nel contesto di esecuzione.")

    model = YOLO(model_path)
    names = model.names
    if isinstance(names, dict):
        return [names[k] for k in sorted(names)]
    return list(names)


@dataclass(frozen=True)
class StereoConfig:
    """Parametri geometrici del sistema stereo-fotogrammetrico."""
    baseline_mm: float = 60.0
    focal_length_px: float = 1400.0
    mm_per_px_at_1m: Optional[float] = None


@dataclass
class ObjectDetection:
    """Rappresentazione metrologica di un oggetto rilevato."""
    pair_timestamp: str
    label: str
    confidence: float
    bbox_xyxy: Tuple[int, int, int, int]
    contour: np.ndarray
    ellipse: Tuple[Tuple[float, float], Tuple[float, float], float]
    length_mm: float
    width_mm: float
    depth_mm: Optional[float] = None
    track_id: Optional[str] = None  # es. "P-1"


@dataclass
class PairResult:
    """Risultato dell'elaborazione di una coppia di fotogrammi stereo."""
    timestamp: str
    right_image: np.ndarray
    left_image: Optional[np.ndarray] = None
    detections: List[ObjectDetection] = field(default_factory=list)
    overlay_image: Optional[np.ndarray] = None


class ObjectAnalyzer:
    """Pipeline per la rilevazione, segmentazione e misurazione di elementi target."""

    def __init__(
            self,
            model_path: str,
            stereo_config: Optional[StereoConfig] = None,
            device: Optional[str] = None
    ) -> None:
        if YOLO is None:
            raise ImportError("Modulo 'ultralytics' non disponibile nel contesto di esecuzione.")

        self.device = device or select_computation_device()
        self.model = YOLO(model_path)
        self.stereo_config = stereo_config or StereoConfig()

    def _estimate_depth(
            self,
            right_img: np.ndarray,
            left_img: np.ndarray,
            bbox: Tuple[int, int, int, int]
    ) -> Optional[float]:
        return None

    def _get_scale_factor(self, depth_mm: Optional[float]) -> float:
        cfg = self.stereo_config
        if depth_mm and cfg.focal_length_px:
            return depth_mm / cfg.focal_length_px
        if cfg.mm_per_px_at_1m:
            return cfg.mm_per_px_at_1m
        return 1.0

    def analyze_pair(
            self,
            timestamp: str,
            right_path: Path,
            left_path: Path,
            target_label: Optional[str] = None,
    ) -> PairResult:
        """
        Esegue la rilevazione sulla CAMERA SINISTRA (lx).
        """
        right_img = cv2.imread(str(right_path))
        left_img = cv2.imread(str(left_path))

        if right_img is None or left_img is None:
            raise FileNotFoundError(f"Errore nella lettura dei file: {right_path} o {left_path}")

        result = PairResult(timestamp=timestamp, right_image=right_img, left_image=left_img)

        # Predict eseguito su LEFT_IMG
        predictions = self.model.predict(left_img, device=self.device, verbose=False)[0]
        target_label_lower = target_label.strip().lower() if target_label else None

        if predictions.masks is not None:
            for mask_xy, box in zip(predictions.masks.xy, predictions.boxes):
                contour = mask_xy.astype(np.int32).reshape(-1, 1, 2)
                if len(contour) < 5:
                    continue

                ellipse = cv2.fitEllipse(contour)
                _, (major_px, minor_px), _ = ellipse

                bbox = tuple(int(v) for v in box.xyxy[0].tolist())
                confidence = float(box.conf[0])
                cls_id = int(box.cls[0])

                class_name = (
                    predictions.names.get(cls_id, f"Class_{cls_id}")
                    if hasattr(predictions, "names")
                    else f"Class_{cls_id}"
                )

                if target_label_lower is not None and class_name.strip().lower() != target_label_lower:
                    continue

                depth_mm = self._estimate_depth(right_img, left_img, bbox)
                scale = self._get_scale_factor(depth_mm)

                detection = ObjectDetection(
                    pair_timestamp=timestamp,
                    label=class_name,
                    confidence=confidence,
                    bbox_xyxy=bbox,
                    contour=contour,
                    ellipse=ellipse,
                    length_mm=major_px * scale,
                    width_mm=minor_px * scale,
                    depth_mm=depth_mm,
                )
                result.detections.append(detection)

        return result


def render_overlay(
    image: np.ndarray,
    detections: List[ObjectDetection],
    filter_ids: Optional[Set[str]] = None
) -> np.ndarray:
    """
    Disegna maschere ed etichette. Se filter_ids è fornito, mostra SOLO
    gli oggetti aventi track_id presente in filter_ids.
    """
    overlay = image.copy()

    for detection in detections:
        if filter_ids is not None and detection.track_id not in filter_ids:
            continue

        cv2.drawContours(overlay, [detection.contour], -1, (0, 255, 0), 2)
        cv2.ellipse(overlay, detection.ellipse, (0, 165, 255), 2)

        id_str = f"[{detection.track_id}] " if detection.track_id else ""
        caption = f"{id_str}{detection.label}"

        # Sfondo nero per rendere la scritta sempre ben visibile
        txt_size, _ = cv2.getTextSize(caption, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        tx, ty = detection.bbox_xyxy[0], max(detection.bbox_xyxy[1] - 8, 20)
        cv2.rectangle(overlay, (tx, ty - txt_size[1] - 4), (tx + txt_size[0] + 4, ty + 4), (0, 0, 0), -1)

        cv2.putText(
            overlay,
            caption,
            (tx + 2, ty),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )

    return overlay