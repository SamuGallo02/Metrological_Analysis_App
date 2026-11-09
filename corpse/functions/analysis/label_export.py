"""Turns the detections of an analysis into YOLO label lines, ready to be stored with `common.label_store`.

The polygon of each detected object (segmentation) is saved, or its box when the contour is too small to be a polygon.
Class numbers follow the model's own class list; a class the model does not list is appended, so numbers never change
within a set of labels."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Union

import cv2
import numpy as np

from common.label_store import save_labels, yolo_box_line, yolo_polygon_line

log = logging.getLogger("analysis.labels")
MAX_POINTS = 200                       # a contour is simplified to keep the label files small


def model_class_names(analyzer: Any) -> List[str]:
    """The class names of an analyzer's YOLO model, in order of class number (empty if it cannot tell)."""
    names = getattr(getattr(analyzer, "model", None), "names", None)
    if isinstance(names, dict):
        return [str(names[k]) for k in sorted(names)]
    if isinstance(names, (list, tuple)):
        return [str(n) for n in names]
    return []


class LabelRecorder:
    def __init__(self, classes: Iterable[str] = ()):
        self.classes: List[str] = list(classes)

    def class_id(self, label: str) -> int:
        wanted = label.strip().lower()
        for i, name in enumerate(self.classes):
            if name.strip().lower() == wanted:
                return i
        self.classes.append(label.strip())
        return len(self.classes) - 1

    @staticmethod
    def _polygon(contour: Optional[np.ndarray]) -> Optional[np.ndarray]:
        if contour is None or len(contour) < 3:
            return None
        pts = np.asarray(contour, dtype=np.int32).reshape(-1, 1, 2)
        if len(pts) > MAX_POINTS:
            pts = cv2.approxPolyDP(pts, 0.002 * cv2.arcLength(pts, True), True)
        return pts.reshape(-1, 2) if len(pts) >= 3 else None

    def lines_for(self, detections: Sequence[Any], width: int, height: int, frame: Optional[int] = None) -> List[str]:
        """One label line per detection; for video the frame number goes in front."""
        lines: List[str] = []
        for det in detections:
            cls = self.class_id(det.label)
            poly = self._polygon(getattr(det, "contour", None))
            line = (yolo_polygon_line(cls, poly, width, height) if poly is not None
                    else yolo_box_line(cls, det.bbox_xyxy, width, height))
            lines.append(line if frame is None else f"{frame} {line}")
        return lines


def save_media_labels(media: Union[str, Path], lines: Sequence[str], classes: Sequence[str]) -> None:
    """Stores the labels of an analysed photo or video. A failure to write them never stops the analysis."""
    try:
        save_labels(media, lines, classes)
    except OSError:
        log.warning("could not save the labels of %s", media, exc_info=True)
