"""
Modulo di Tracking Multi-Frame Avanzato (IoU + Centroide)
==========================================================
Garantisce la continuita temporale degli ID evitando re-assegnazioni errate
grazie all'algoritmo di corrispondenza ottimale (Hungarian Matching / Greedy IoU).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
import numpy as np

from core.analysis import ObjectDetection

MAX_MATCH_DISTANCE_PX = 250.0  # Tolleranza di movimento espansa per frame distanziati
MAX_MISSED_FRAMES = 10        # Mantiene in memoria la traccia piu a lungo se la detection cede
MIN_IOU_THRESHOLD = 0.15       # Soglia minima di sovrapposizione per considerare lo stesso oggetto


@dataclass
class _Track:
    track_id: str
    label: str
    bbox: Tuple[int, int, int, int]
    centroid: Tuple[float, float]
    missed_frames: int = 0


class ObjectTracker:
    """
    Assegna ID univoci formattati per tipologia di soggetto (es. P-1, C-1)
    e gestisce il tracciamento multi-frame ad alta stabilita.
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
        """Azzera lo stato del tracker."""
        self._active_tracks.clear()
        self._class_counters.clear()
        self.total_count = 0

    def _generate_next_id(self, label: str) -> str:
        """Genera un ID univoco del tipo 'P-1' basato sul tipo di soggetto."""
        clean_label = label.strip().lower()
        prefix = clean_label[0].upper() if clean_label else "OBJ"

        current_num = self._class_counters.get(clean_label, 0) + 1
        self._class_counters[clean_label] = current_num

        return f"{prefix}-{current_num}"

    @staticmethod
    def _compute_iou(boxA: Tuple[int, int, int, int], boxB: Tuple[int, int, int, int]) -> float:
        """Calcola l'Intersection over Union (IoU) tra due Bounding Box."""
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

        # Costruzione matrice dei costi/punteggi tra tracce attive e nuove rilevazioni
        num_tracks = len(self._active_tracks)
        num_dets = len(detections)

        matched_dets: Set[int] = set()
        matched_tracks: Set[int] = set()

        if num_tracks > 0 and num_dets > 0:
            # Calcolo matrice delle similarita (IoU + Distanza)
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
                        # Punteggio combinato: favorisce alta IoU e bassa distanza
                        dist_score = max(0.0, 1.0 - (dist / self.max_match_distance_px))
                        scores[t_idx, d_idx] = iou * 0.7 + dist_score * 0.3

            # Assegnazione Greedy basata sui punteggi piu alti
            while True:
                max_score = np.max(scores)
                if max_score < 0:
                    break

                t_idx, d_idx = np.unravel_index(np.argmax(scores), scores.shape)

                # Assegna l'ID
                track = self._active_tracks[t_idx]
                det = detections[d_idx]

                det.track_id = track.track_id
                track.bbox = det.bbox_xyxy
                track.centroid = self._centroid_of(det)
                track.missed_frames = 0

                matched_tracks.add(t_idx)
                matched_dets.add(d_idx)

                # Annulla la riga e la colonna utilizzate
                scores[t_idx, :] = -1.0
                scores[:, d_idx] = -1.0

        # Crea nuove tracce per le rilevazioni non associate
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

        # Aggiorna missed frames per le tracce non abbinate
        for t_idx, track in enumerate(self._active_tracks):
            if t_idx not in matched_tracks and track.missed_frames > 0:
                track.missed_frames += 1

        # Mantiene solo le tracce non scadute
        self._active_tracks = [t for t in self._active_tracks if t.missed_frames <= self.max_missed_frames]