"""
Photogrammetric Analysis and Segmentation Module
=================================================

Autore: Samuele Gallo
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
    """Determines the best hardware accelerator available on the system."""
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
    """Loads a YOLO model and returns the exact list of known classes."""
    if YOLO is None:
        raise ImportError("Modulo 'ultralytics' non disponibile nel contesto di esecuzione.")

    model = YOLO(model_path)
    names = model.names
    if isinstance(names, dict):
        return [names[k] for k in sorted(names)]
    return list(names)


def _extract_raw_detections(predictions, timestamp: str) -> List["ObjectDetection"]:
    """
    Extracts the raw ObjectDetection items (contour, ellipse, class, confidence) from
    a YOLO prediction result — WITHOUT any estimate of real depth/dimensions,
    which requires a second camera and is added separately by the caller of
    this function when (and only when) a stereo pair is available.
    Shared by analyze_pair (stereo photo), analyze_single_image (single photo)
    and ObjectAnalyzer.detect_in_image (one video frame at a time).
    """
    detections: List[ObjectDetection] = []
    if predictions.masks is None:
        return detections

    for mask_xy, box in zip(predictions.masks.xy, predictions.boxes):
        contour = mask_xy.astype(np.int32).reshape(-1, 1, 2)
        if len(contour) < 5:
            continue

        ellipse = cv2.fitEllipse(contour)
        bbox = tuple(int(v) for v in box.xyxy[0].tolist())
        confidence = float(box.conf[0])
        cls_id = int(box.cls[0])

        class_name = (
            predictions.names.get(cls_id, f"Class_{cls_id}")
            if hasattr(predictions, "names")
            else f"Class_{cls_id}"
        )

        detections.append(ObjectDetection(
            pair_timestamp=timestamp,
            label=class_name,
            confidence=confidence,
            bbox_xyxy=bbox,
            contour=contour,
            ellipse=ellipse,
            length_mm=None,
            width_mm=None,
        ))

    return detections


@dataclass(frozen=True)
class StereoConfig:
    """Geometric parameters of the stereo-photogrammetric system."""
    baseline_mm: float = 60.0
    focal_length_px: float = 1400.0


@dataclass
class ObjectDetection:
    """Metrological representation of a detected object."""
    pair_timestamp: str
    label: str
    confidence: float
    bbox_xyxy: Tuple[int, int, int, int]
    contour: np.ndarray
    ellipse: Tuple[Tuple[float, float], Tuple[float, float], float]
    length_mm: Optional[float]
    width_mm: Optional[float]
    depth_mm: Optional[float] = None
    contact_distance_mm: Optional[float] = None  # real distance (stereo triangulation) to the subject's contact point/base
    track_id: Optional[str] = None  # e.g. "P-1"


@dataclass
class PairResult:
    """Result of processing a pair of stereo frames."""
    timestamp: str
    right_image: np.ndarray
    left_image: Optional[np.ndarray] = None
    detections: List[ObjectDetection] = field(default_factory=list)
    overlay_image: Optional[np.ndarray] = None


class ObjectAnalyzer:
    """Pipeline for detecting, segmenting and measuring target elements."""

    def __init__(
            self,
            model_path: str,
            stereo_config: Optional[StereoConfig] = None,
            device: Optional[str] = None,
    ) -> None:
        if YOLO is None:
            raise ImportError("Modulo 'ultralytics' non disponibile nel contesto di esecuzione.")

        self.device = device or select_computation_device()
        self.model = YOLO(model_path)
        self.stereo_config = stereo_config or StereoConfig()

        # Persistent stereo matcher: created once, reused for every pair.
        # NOTE: assumes already RECTIFIED images (parallel optical axes, horizontal
        # epipolar lines). With two lenses mechanically fixed on the same
        # plane this is often a good approximation, but for maximum
        # accuracy a full stereo calibration would be needed (cv2.stereoCalibrate
        # + cv2.stereoRectify) to correct any residual misalignment/distortion.
        # If you later get the real calibration matrices, this is where
        # the rectification should be applied before computing the disparity.
        self._stereo_matcher = cv2.StereoSGBM_create(
            minDisparity=0,
            numDisparities=128,
            blockSize=7,
            P1=8 * 3 * 7 ** 2,
            P2=32 * 3 * 7 ** 2,
            disp12MaxDiff=1,
            uniquenessRatio=10,
            speckleWindowSize=100,
            speckleRange=32,
        )

    def _compute_disparity_map(self, left_img: np.ndarray, right_img: np.ndarray) -> Optional[np.ndarray]:
        """Computes the disparity map between the two lenses (left as reference)."""
        if self.stereo_config.baseline_mm <= 0 or self.stereo_config.focal_length_px <= 0:
            return None

        gray_left = cv2.cvtColor(left_img, cv2.COLOR_BGR2GRAY)
        gray_right = cv2.cvtColor(right_img, cv2.COLOR_BGR2GRAY)

        raw_disparity = self._stereo_matcher.compute(gray_left, gray_right)
        return raw_disparity.astype(np.float32) / 16.0  # StereoSGBM returns disparity in 4-bit fixed point

    def _depth_from_disparity(
            self,
            disparity_map: Optional[np.ndarray],
            x: int,
            y: int,
            window: int = 3,
    ) -> Optional[float]:
        """
        Estimates the real depth (mm) at point (x, y) of the left image
        via triangulation: depth = (baseline_mm * focal_length_px) / disparity.
        Samples a small window around the point (median) for robustness
        against local stereo-matching noise.
        """
        if disparity_map is None:
            return None

        h, w = disparity_map.shape
        x0, x1 = max(0, x - window), min(w, x + window + 1)
        y0, y1 = max(0, y - window), min(h, y + window + 1)
        region = disparity_map[y0:y1, x0:x1]

        valid = region[region > 0]  # disparity <= 0 = match not found/invalid
        if valid.size == 0:
            return None

        disparity_px = float(np.median(valid))
        return (self.stereo_config.baseline_mm * self.stereo_config.focal_length_px) / disparity_px

    def _get_scale_factor(self, depth_mm: Optional[float]) -> Optional[float]:
        """
        Returns the mm/px factor to apply to pixel dimensions, or
        None if there is no valid stereo depth at that point — NEVER an
        approximate fallback, which would introduce an error proportional to how far
        the subject really is from the implicit assumption.
        """
        cfg = self.stereo_config
        if depth_mm and cfg.focal_length_px:
            return depth_mm / cfg.focal_length_px
        return None

    def analyze_pair(
            self,
            timestamp: str,
            right_path: Path,
            left_path: Path,
            target_label: Optional[str] = None,
    ) -> PairResult:
        """
        Reads a pair of stereo images from disk and runs analyze_frame_pair.
        """
        right_img = cv2.imread(str(right_path))
        left_img = cv2.imread(str(left_path))

        if right_img is None or left_img is None:
            raise FileNotFoundError(f"Errore nella lettura dei file: {right_path} o {left_path}")

        return self.analyze_frame_pair(timestamp, right_img, left_img, target_label=target_label)

    def analyze_frame_pair(
            self,
            timestamp: str,
            right_img: np.ndarray,
            left_img: np.ndarray,
            target_label: Optional[str] = None,
    ) -> PairResult:
        """
        Runs the whole stereo pipeline (disparity + detection + measurements) on a
        pair of images ALREADY IN MEMORY. Used both by analyze_pair (images
        read from disk) and by the stereo-video analysis (frames read from two
        synchronized VideoCapture objects) — so the measurement logic is just ONE,
        shared by both paths instead of being duplicated.
        Runs detection on the LEFT CAMERA (lx).
        """
        result = PairResult(timestamp=timestamp, right_image=right_img, left_image=left_img)

        # Disparity map computed ONCE per pair (not per detection):
        # it is the most expensive operation, so reuse it for all subjects in the frame.
        disparity_map = self._compute_disparity_map(left_img, right_img)

        # Predict run on LEFT_IMG
        predictions = self.model.predict(left_img, device=self.device, verbose=False)[0]
        target_label_lower = target_label.strip().lower() if target_label else None

        for detection in _extract_raw_detections(predictions, timestamp):
            if target_label_lower is not None and detection.label.strip().lower() != target_label_lower:
                continue

            bbox = detection.bbox_xyxy
            _, (major_px, minor_px), _ = detection.ellipse

            depth_mm = self._depth_from_disparity(
                disparity_map, (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2
            )
            scale = self._get_scale_factor(depth_mm)
            detection.length_mm = major_px * scale if scale is not None else None
            detection.width_mm = minor_px * scale if scale is not None else None
            detection.depth_mm = depth_mm

            # Distance at the contact point: REAL depth (stereo
            # triangulation) at the point where the subject touches the surface below
            # (bottom of the bounding box). If stereo matching fails at
            # that point (e.g. a low-texture area), it stays None: no
            # geometric fallback estimate, to avoid introducing error from an
            # inclination angle that is hard to measure accurately.
            detection.contact_distance_mm = self._depth_from_disparity(
                disparity_map, (bbox[0] + bbox[2]) // 2, bbox[3]
            )

            result.detections.append(detection)

        return result

    def detect_in_image(self, image: np.ndarray, timestamp: str) -> List[ObjectDetection]:
        """
        Detects and segments the subjects in a single image already in memory
        (used by the video flow, one frame at a time). No estimate of
        real depth/dimensions: there is no second camera here with which to
        triangulate, exactly as for single-photo analysis.
        """
        predictions = self.model.predict(image, device=self.device, verbose=False)[0]
        return _extract_raw_detections(predictions, timestamp)


def analyze_single_image(model_path: str, image_path: Path) -> Tuple[np.ndarray, List[ObjectDetection]]:
    """
    Detects and segments the subjects in a single photo (no stereo pair
    available): no estimate of real depth/dimensions, only
    mask, class and confidence. Loads the model only once for
    the whole call (occasional use, unlike the video flow, which
    reuses an already instantiated ObjectAnalyzer across many frames).
    """
    if YOLO is None:
        raise ImportError("Modulo 'ultralytics' non disponibile nel contesto di esecuzione.")

    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Errore nella lettura del file immagine: {image_path}")

    model = YOLO(model_path)
    device = select_computation_device()
    predictions = model.predict(image, device=device, verbose=False)[0]

    detections = _extract_raw_detections(predictions, timestamp=Path(image_path).stem)
    return image, detections


def render_overlay(
    image: np.ndarray,
    detections: List[ObjectDetection],
    filter_ids: Optional[Set[str]] = None
) -> np.ndarray:
    """
    Draws masks and labels. If filter_ids is provided, shows ONLY
    the objects whose track_id is in filter_ids.
    """
    overlay = image.copy()

    for detection in detections:
        if filter_ids is not None and detection.track_id not in filter_ids:
            continue

        cv2.drawContours(overlay, [detection.contour], -1, (0, 255, 0), 2)
        "cv2.ellipse(overlay, detection.ellipse, (0, 165, 255), 2)"

        id_str = f"[{detection.track_id}] " if detection.track_id else ""
        caption = f"{id_str}{detection.label}"

        # Black background so the text is always clearly visible
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