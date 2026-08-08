"""
Modulo per l'Analisi Stereo-Fotogrammetrica Metrologica
=======================================================
Esegue la rilevazione, la segmentazione tramite YOLO e il calcolo delle dimensioni 3D
sulle coppie di immagini stereo integrando la logica di 'cup dimension'.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
import torch
from ultralytics import YOLO


@dataclass
class DetectionResult:
    label: str
    confidence: float
    length_mm: float
    width_mm: float
    distance_cm: float


# Alias per retrocompatibilità
ObjectDetection = DetectionResult


@dataclass
class PairResult:
    timestamp: str
    left_image: cv2.Mat
    right_image: cv2.Mat
    overlay_image: cv2.Mat
    mask_overlay_left: cv2.Mat
    detections: List[DetectionResult]


@dataclass
class StereoConfig:
    focal_length: float = 140.0
    baseline_cm: float = 10.0
    depth_w: int = 640
    depth_h: int = 360


class ObjectAnalyzer:
    def __init__(self, model_path: str, config: StereoConfig = StereoConfig()) -> None:
        self.config = config
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.model = YOLO(model_path)
        self.model.to(self.device)
        self.model.fuse()

        self.stereo = cv2.StereoSGBM_create(
            minDisparity=0,
            numDisparities=96,
            blockSize=7,
            P1=8 * 3 * 7**2,
            P2=32 * 3 * 7**2,
            disp12MaxDiff=1,
            uniquenessRatio=8,
            speckleWindowSize=50,
            speckleRange=16,
            mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY,
        )

    def _get_depth_map(self, img_left_gray: cv2.Mat, img_right_gray: cv2.Mat) -> np.ndarray:
        small_left = cv2.resize(img_left_gray, (self.config.depth_w, self.config.depth_h))
        small_right = cv2.resize(img_right_gray, (self.config.depth_w, self.config.depth_h))

        disparity = self.stereo.compute(small_left, small_right).astype(np.float32) / 16.0

        with np.errstate(divide="ignore", invalid="ignore"):
            depth_small = np.where(
                disparity > 0,
                (self.config.focal_length * self.config.baseline_cm) / disparity,
                0,
            )

        h, w = img_left_gray.shape[:2]
        return cv2.resize(depth_small, (w, h), interpolation=cv2.INTER_LINEAR)

    def _get_distance_from_mask(self, depth_map: np.ndarray, mask_bin: np.ndarray) -> Optional[float]:
        ys, xs = np.where(mask_bin == 255)
        if len(xs) == 0:
            return None

        indices = np.random.choice(len(xs), min(300, len(xs)), replace=False)
        values = [depth_map[ys[idx], xs[idx]] for idx in indices if depth_map[ys[idx], xs[idx]] > 0]

        if not values:
            return None

        arr = np.array(values)
        q1, q3 = np.percentile(arr, [25, 75])
        iqr = q3 - q1

        filtered = arr[(arr >= q1 - 1.5 * iqr) & (arr <= q3 + 1.5 * iqr)]
        return float(np.median(filtered if len(filtered) > 0 else arr))

    def _pixels_to_cm(self, pixels: float, distance_cm: float) -> float:
        return (pixels * distance_cm) / self.config.focal_length

    def _get_dimensions_cup_style(
        self, mask_bin: np.ndarray, distance_cm: float, depth_map: np.ndarray
    ) -> Tuple[Optional[float], Optional[float], Optional[np.ndarray]]:
        """Calcola dimensioni (in mm) usando l'algoritmo geometrico 3D da 'cup dimension'."""
        contours, _ = cv2.findContours(mask_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None, None, None

        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        contour = contours[0]

        if cv2.contourArea(contour) < 100:
            return None, None, None

        epsilon = 0.01 * cv2.arcLength(contour, True)
        contour = cv2.approxPolyDP(contour, epsilon, True)

        if len(contour) >= 5:
            ellipse = cv2.fitEllipse(contour)
            (cx, cy), (w_px, h_px), angle = ellipse
            rect = ((cx, cy), (w_px, h_px), angle)
        else:
            rect = cv2.minAreaRect(contour)
            (cx, cy), (w_px, h_px), angle = rect

        box_pts = cv2.boxPoints(rect).astype(np.int32)

        if w_px < h_px:
            w_px, h_px = h_px, w_px

        cx, cy = int(cx), int(cy)
        top_y = max(0, cy - int(h_px / 2))
        bot_y = min(depth_map.shape[0] - 1, cy + int(h_px / 2))

        d_top = depth_map[top_y, np.clip(cx, 0, depth_map.shape[1] - 1)]
        d_bot = depth_map[bot_y, np.clip(cx, 0, depth_map.shape[1] - 1)]

        h_cm_2d = self._pixels_to_cm(h_px, distance_cm)
        w_cm_2d = self._pixels_to_cm(w_px, distance_cm)

        delta_d = abs(float(d_top) - float(d_bot)) if (d_top > 0 and d_bot > 0) else 0.0

        h_cm = np.sqrt(h_cm_2d**2 + delta_d**2)

        # Conversione finale da centimetri a millimetri per reportistica
        return float(h_cm * 10.0), float(w_cm_2d * 10.0), box_pts

    def analyze_pair(
        self, timestamp: str, right_path: Path, left_path: Path, target_label: Optional[str] = None
    ) -> PairResult:
        img_left = cv2.imread(str(left_path))
        img_right = cv2.imread(str(right_path))

        if img_left is None or img_right is None:
            raise ValueError(f"Impossibile caricare le immagini per il timestamp: {timestamp}")

        gray_left = cv2.cvtColor(img_left, cv2.COLOR_BGR2GRAY)
        gray_right = cv2.cvtColor(img_right, cv2.COLOR_BGR2GRAY)

        depth_map = self._get_depth_map(gray_left, gray_right)

        results = self.model.predict(
            source=img_left,
            conf=0.35,
            iou=0.5,
            retina_masks=True,
            verbose=False,
            device=0 if self.device == "cuda" else "cpu",
        )

        detections: List[DetectionResult] = []
        left_mask_visual = img_left.copy()
        h_img, w_img = img_left.shape[:2]

        for r in results:
            if r.boxes is None or len(r.boxes) == 0:
                continue

            for i, box in enumerate(r.boxes):
                cls_id = int(box.cls[0])
                label = self.model.names[cls_id]

                # Filtro obbligatorio sulla singola classe selezionata
                if target_label and label.lower().strip() != target_label.lower().strip():
                    continue

                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])

                length_mm, width_mm, distance_cm = 0.0, 0.0, 0.0
                box_pts = None

                # --- ELABORAZIONE MASCHERA SECONDO LO SCRIPT CUP DIMENSION ---
                if r.masks is not None and len(r.masks) > i:
                    try:
                        mask = r.masks.data.cpu().numpy()[i]
                        mask_resized = cv2.resize(mask, (w_img, h_img), interpolation=cv2.INTER_LINEAR)
                        mask_bin = (mask_resized > 0.5).astype(np.uint8) * 255

                        # 1. Pulizia morfologica avanzata
                        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
                        mask_bin = cv2.morphologyEx(mask_bin, cv2.MORPH_OPEN, kernel, iterations=2)
                        mask_bin = cv2.morphologyEx(mask_bin, cv2.MORPH_CLOSE, kernel, iterations=2)

                        # 2. Selezione componente connessa maggiore (filtra il rumore secondario)
                        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask_bin)
                        if num_labels > 1:
                            largest = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
                            clean_mask = np.zeros_like(mask_bin)
                            clean_mask[labels == largest] = 255
                            mask_bin = clean_mask

                        # 3. Sfocatura e binarizzazione di precisione
                        mask_bin = cv2.GaussianBlur(mask_bin, (5, 5), 0)
                        _, mask_bin = cv2.threshold(mask_bin, 127, 255, cv2.THRESH_BINARY)

                        dist_est = self._get_distance_from_mask(depth_map, mask_bin)

                        if dist_est is not None:
                            distance_cm = dist_est
                            l_mm, w_mm, b_pts = self._get_dimensions_cup_style(mask_bin, distance_cm, depth_map)
                            if l_mm is not None and w_mm is not None:
                                length_mm, width_mm = l_mm, w_mm
                                box_pts = b_pts

                        # 4. Sovrapposizione grafica della maschera verde su immagine di SINISTRA
                        mask_overlay = left_mask_visual.copy()
                        mask_overlay[mask_bin == 255] = (0, 255, 0)
                        left_mask_visual = cv2.addWeighted(mask_overlay, 0.35, left_mask_visual, 0.65, 0)
                    except Exception:
                        pass

                # --- DISEGNO ELEMENTI GRAFICI SU IMMAGINE DI SINISTRA ---

                # Bounding Box rettangolare YOLO
                cv2.rectangle(left_mask_visual, (x1, y1), (x2, y2), (0, 255, 0), 2)

                # Contorno orientato del box metrologico (Giallo) e centroide
                if box_pts is not None:
                    cv2.drawContours(left_mask_visual, [box_pts], 0, (0, 255, 255), 2)

                # Etichette e misurazioni
                dist_str = f"{distance_cm:.1f}cm" if distance_cm > 0 else "N/A"
                text_top = f"{label} {conf:.2f} | {dist_str}"

                (w_text, _), _ = cv2.getTextSize(text_top, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                cv2.rectangle(left_mask_visual, (x1, max(0, y1 - 25)), (x1 + w_text, y1), (0, 0, 0), -1)
                cv2.putText(
                    left_mask_visual,
                    text_top,
                    (x1, max(15, y1 - 7)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 0),
                    2,
                )

                if length_mm > 0:
                    text_dim = f"H:{length_mm/10.0:.1f}cm W:{width_mm/10.0:.1f}cm ({length_mm:.1f}x{width_mm:.1f}mm)"
                    (w_dim, _), _ = cv2.getTextSize(text_dim, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                    cv2.rectangle(left_mask_visual, (x1, y1), (x1 + w_dim, y1 + 20), (0, 0, 0), -1)
                    cv2.putText(
                        left_mask_visual,
                        text_dim,
                        (x1, y1 + 15),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (0, 200, 255),
                        2,
                    )

                detections.append(
                    DetectionResult(
                        label=label,
                        confidence=conf,
                        length_mm=length_mm,
                        width_mm=width_mm,
                        distance_cm=distance_cm,
                    )
                )

        return PairResult(
            timestamp=timestamp,
            left_image=img_left,
            right_image=img_right,
            overlay_image=left_mask_visual,
            mask_overlay_left=left_mask_visual,
            detections=detections,
        )