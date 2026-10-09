"""
Advanced Multi-Frame Tracking Module (IoU + Centroid)
==========================================================
Ensures temporal continuity of IDs, avoiding wrong re-assignments
thanks to the optimal matching algorithm (Hungarian Matching / Greedy IoU).

Autore: Samuele Gallo
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
import numpy as np

from corpse.functions.analysis.analysis import ObjectDetection


def generate_adaptive_prefixes(class_labels: List[str]) -> Dict[str, str]:
    """
    Generates a dictionary {class_name: formatted_unique_prefix} adaptively
    (e.g. 'B', 'Ce'), used by all analysis pages to
    format tracking IDs (e.g. "Ce-1").
    """
    cleaned_map = {label: "".join(c for c in label.lower() if c.isalnum()) or "obj" for label in set(class_labels)}
    prefixes: Dict[str, str] = {}

    for original_label, cleaned in cleaned_map.items():
        length = 1
        while True:
            candidate = cleaned[:length]
            if candidate not in prefixes.values() or length >= len(cleaned):
                prefixes[original_label] = candidate.capitalize()
                break
            length += 1

    return prefixes

MAX_MATCH_DISTANCE_PX = 250.0  # Expanded movement tolerance for widely spaced frames
MAX_MISSED_FRAMES = 10        # Keeps the track in memory longer if detection drops out
MIN_IOU_THRESHOLD = 0.15       # Minimum overlap threshold to consider it the same object


@dataclass
class _Track:
    track_id: str
    label: str
    bbox: Tuple[int, int, int, int]
    centroid: Tuple[float, float]
    missed_frames: int = 0


class ObjectTracker:
    """
    Assigns unique formatted IDs by subject type (e.g. P-1, C-1)
    and handles high-stability multi-frame tracking.
    """

    def __init__(
            self,
            max_match_distance_px: float = MAX_MATCH_DISTANCE_PX,
            max_missed_frames: int = MAX_MISSED_FRAMES,
            iou_threshold: float = MIN_IOU_THRESHOLD,
    ) -> None:
        self.max_match_distance_px = max_match_distance_px
        self.max_missed_frames = max_missed_frames
        self.iou_threshold = iou_threshold

        self._active_tracks: List[_Track] = []
        self._class_counters: Dict[str, int] = {}
        self.total_count: int = 0

    def reset(self) -> None:
        """Resets the tracker state."""
        self._active_tracks.clear()
        self._class_counters.clear()
        self.total_count = 0

    def _generate_next_id(self, label: str) -> str:
        """Generates a unique ID such as 'P-1' based on the subject type."""
        clean_label = label.strip().lower()
        prefix = clean_label[0].upper() if clean_label else "OBJ"

        current_num = self._class_counters.get(clean_label, 0) + 1
        self._class_counters[clean_label] = current_num

        return f"{prefix}-{current_num}"

    @staticmethod
    def _compute_iou(boxA: Tuple[int, int, int, int], boxB: Tuple[int, int, int, int]) -> float:
        """Computes the Intersection over Union (IoU) between two bounding boxes."""
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])

        interArea = max(0, xB - xA) * max(0, yB - yA)
        if interArea == 0:
            return 0.0

        boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])

        iou = interArea / float(boxAArea + boxBArea - interArea)
        return iou

    @staticmethod
    def _centroid_of(det: ObjectDetection) -> Tuple[float, float]:
        box = det.bbox_xyxy
        return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)

    def update(self, detections: List[ObjectDetection]) -> None:
        if not detections:
            for track in self._active_tracks:
                track.missed_frames += 1
            self._active_tracks = [t for t in self._active_tracks if t.missed_frames <= self.max_missed_frames]
            return

        # Build the cost/score matrix between active tracks and new detections
        num_tracks = len(self._active_tracks)
        num_dets = len(detections)

        matched_dets: Set[int] = set()
        matched_tracks: Set[int] = set()

        if num_tracks > 0 and num_dets > 0:
            # Compute the similarity matrix (IoU + distance)
            scores = np.zeros((num_tracks, num_dets), dtype=np.float32)

            for t_idx, track in enumerate(self._active_tracks):
                for d_idx, det in enumerate(detections):
                    if track.label.lower() != det.label.lower():
                        scores[t_idx, d_idx] = -1.0
                        continue

                    iou = self._compute_iou(track.bbox, det.bbox_xyxy)
                    det_center = self._centroid_of(det)
                    dist = ((det_center[0] - track.centroid[0])**2 + (det_center[1] - track.centroid[1])**2)**0.5

                    if dist > self.max_match_distance_px and iou < self.iou_threshold:
                        scores[t_idx, d_idx] = -1.0
                    else:
                        # Combined score: favors high IoU and low distance
                        dist_score = max(0.0, 1.0 - (dist / self.max_match_distance_px))
                        scores[t_idx, d_idx] = iou * 0.7 + dist_score * 0.3

            # Greedy assignment based on the highest scores
            while True:
                max_score = np.max(scores)
                if max_score < 0:
                    break

                t_idx, d_idx = np.unravel_index(np.argmax(scores), scores.shape)

                # Assign the ID
                track = self._active_tracks[t_idx]
                det = detections[d_idx]

                det.track_id = track.track_id
                track.bbox = det.bbox_xyxy
                track.centroid = self._centroid_of(det)
                track.missed_frames = 0

                matched_tracks.add(t_idx)
                matched_dets.add(d_idx)

                # Clear the row and column used
                scores[t_idx, :] = -1.0
                scores[:, d_idx] = -1.0

        # Create new tracks for unmatched detections
        for d_idx, det in enumerate(detections):
            if d_idx not in matched_dets:
                new_id = self._generate_next_id(det.label)
                new_track = _Track(
                    track_id=new_id,
                    label=det.label,
                    bbox=det.bbox_xyxy,
                    centroid=self._centroid_of(det)
                )
                det.track_id = new_track.track_id
                self._active_tracks.append(new_track)
                self.total_count += 1

        # Update missed frames for unmatched tracks
        for t_idx, track in enumerate(self._active_tracks):
            if t_idx not in matched_tracks and track.missed_frames > 0:
                track.missed_frames += 1

        # Keep only the tracks that have not expired
        self._active_tracks = [t for t in self._active_tracks if t.missed_frames <= self.max_missed_frames]