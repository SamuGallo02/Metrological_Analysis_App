"""
Graphical Interface Module for Video Analysis — Stereo mode (two
synchronized videos, left/right). Identical in every respect to
photo Stereo Analysis: same real measurement pipeline (baseline + focal length),
applied frame by frame instead of to single photo pairs. It also
exports an annotated video (left camera) with the masks overlaid.

Autore: Samuele Gallo
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Set, Union

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

from corpse.functions.analysis.analysis import ObjectAnalyzer, PairResult, StereoConfig, render_overlay
from corpse.functions.analysis.pairing import find_stereo_video_pair
from corpse.functions.analysis.label_export import LabelRecorder, model_class_names, save_media_labels
from corpse.functions.analysis.tracking import ObjectTracker, generate_adaptive_prefixes
from corpse.gui.analysis.analysis_page_base import AnalysisPageBase
from corpse.gui.analysis.library_picker import add_folder, on_selected, refresh, remove_selected


class VideoStereoAnalysisWorker(QThread):
    """Analysis thread for a pair of synchronized VIDEOS (left/right), with real measurements."""
    progress = Signal(int, int)
    pair_done = Signal(object, int)
    finished_all = Signal()
    error = Signal(str)

    def __init__(
            self, right_video: Path, left_video: Path, output_video_path: Path, model_path: str,
            target_label: Optional[Union[str, List[str]]] = None, stereo_config: Optional[StereoConfig] = None,
    ) -> None:
        super().__init__()
        self.right_video = right_video
        self.left_video = left_video
        self.output_video_path = output_video_path
        self.model_path = model_path
        self.target_label = target_label
        self.stereo_config = stereo_config or StereoConfig()
        self._stop_requested = False

    def run(self) -> None:
        cap_right = cv2.VideoCapture(str(self.right_video))
        cap_left = cv2.VideoCapture(str(self.left_video))

        if not cap_right.isOpened() or not cap_left.isOpened():
            self.error.emit("Impossibile aprire uno dei due file video sincronizzati.")
            cap_right.release()
            cap_left.release()
            return

        writer = None
        try:
            fps = cap_left.get(cv2.CAP_PROP_FPS) or 25.0
            width = int(cap_left.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap_left.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = min(
                int(cap_left.get(cv2.CAP_PROP_FRAME_COUNT)), int(cap_right.get(cv2.CAP_PROP_FRAME_COUNT))
            )

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(self.output_video_path), fourcc, fps, (width, height))

            analyzer = ObjectAnalyzer(self.model_path, self.stereo_config)
            tracker = ObjectTracker()
            recorder = LabelRecorder(model_class_names(analyzer))
            label_lines: List[str] = []                              # `frame cls ...` for the left video
            seen_classes: Set[str] = set()

            target_labels_lower = None
            if isinstance(self.target_label, str):
                target_labels_lower = {self.target_label.strip().lower()}
            elif isinstance(self.target_label, list):
                target_labels_lower = {t.strip().lower() for t in self.target_label}

            frame_idx = 0
            while True:
                if self._stop_requested:
                    break

                ok_l, left_frame = cap_left.read()
                ok_r, right_frame = cap_right.read()
                if not ok_l or not ok_r:
                    break

                frame_idx += 1
                timestamp = f"frame_{frame_idx:06d}"

                result = analyzer.analyze_frame_pair(timestamp, right_frame, left_frame, target_label=None)
                if target_labels_lower is not None:
                    result.detections = [d for d in result.detections if d.label.strip().lower() in target_labels_lower]

                tracker.update(result.detections)
                for det in result.detections:
                    seen_classes.add(det.label)
                prefix_map = generate_adaptive_prefixes(list(seen_classes))
                for det in result.detections:
                    if det.track_id is not None:
                        prefix = prefix_map.get(det.label, "Obj")
                        num_part = str(det.track_id).split("-")[-1].split("_")[-1]
                        det.track_id = f"{prefix}-{num_part}"

                label_lines.extend(recorder.lines_for(result.detections, left_frame.shape[1], left_frame.shape[0],
                                                      frame_idx))
                result.overlay_image = render_overlay(result.left_image, result.detections)
                writer.write(result.overlay_image)

                self.pair_done.emit(result, tracker.total_count)
                if total_frames > 0:
                    self.progress.emit(frame_idx, total_frames)

            save_media_labels(self.left_video, label_lines, recorder.classes)
            self.finished_all.emit()

        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            cap_right.release()
            cap_left.release()
            if writer is not None:
                writer.release()

    def stop(self) -> None:
        self._stop_requested = True


class VideoStereoAnalysisPage(AnalysisPageBase):
    """Video Analysis — Stereo mode: two synchronized videos (rx/lx), real measurements."""

    def __init__(self, on_home, parent: Optional[object] = None) -> None:
        self.selected_folder: Optional[str] = None
        super().__init__(on_home, "Analisi Video — Stereo", dual_preview=True, show_measurements=True, parent=parent)

    def _build_source_selector_ui(self, layout: QVBoxLayout) -> None:
        dataset_bar = QHBoxLayout()
        lbl_dataset = QLabel("Cartella dataset:")
        lbl_dataset.setFixedWidth(self._label_width)
        dataset_bar.addWidget(lbl_dataset)

        self.folder_combo = QComboBox()
        self.folder_combo.setMinimumWidth(220)
        self.folder_combo.currentIndexChanged.connect(self._on_folder_selection_changed)
        dataset_bar.addWidget(self.folder_combo, stretch=1)

        btn_add_dataset = QPushButton("Aggiungi cartella...")
        btn_add_dataset.clicked.connect(self._add_dataset)
        dataset_bar.addWidget(btn_add_dataset)

        btn_refresh_datasets = QPushButton("Aggiorna elenco")
        btn_refresh_datasets.clicked.connect(self._refresh_datasets)
        dataset_bar.addWidget(btn_refresh_datasets)
        btn_remove_dataset = QPushButton("Rimuovi dall'elenco")
        btn_remove_dataset.setToolTip("Toglie la cartella dall'elenco: i file non vengono cancellati.")
        btn_remove_dataset.clicked.connect(self._remove_dataset)
        dataset_bar.addWidget(btn_remove_dataset)
        layout.addLayout(dataset_bar)

        note = QLabel("La cartella deve contenere le sottocartelle rx/ e lx/, ciascuna con un solo file video.")
        note.setStyleSheet("color: #aaaaaa; font-style: italic;")
        layout.addWidget(note)

        self._refresh_datasets()

    KIND = "video_stereo"

    def _add_dataset(self) -> None:
        """Registers a folder where it is: nothing is copied into the application's folders."""
        add_folder(self, self.KIND, "Seleziona cartella con i due video sincronizzati (rx/lx)",
                   None)

    def _remove_dataset(self) -> None:
        remove_selected(self, self.KIND)

    def _refresh_datasets(self) -> None:
        refresh(self, self.KIND)

    def _on_folder_selection_changed(self, _index: int) -> None:
        on_selected(self, self.KIND)

    def _update_run_button_state(self) -> None:
        if not hasattr(self, "btn_run") or not hasattr(self, "model_combo") or not hasattr(self, "selected_folder"):
            return
        self.btn_run.setEnabled(bool(self.selected_folder) and self.model_combo.isEnabled())

    def _resolve_source(self):
        if not self.selected_folder:
            raise ValueError("Seleziona una cartella dataset valida (con due video sincronizzati in rx/lx).")

        pair = find_stereo_video_pair(Path(self.selected_folder))

        save_path, _ = QFileDialog.getSaveFileName(
            self, "Salva video annotato come",
            str(pair.left_video.with_name(pair.left_video.stem + "_annotato.mp4")),
            "Video MP4 (*.mp4)",
        )
        if not save_path:
            raise ValueError("Esportazione annullata: scegli dove salvare il video annotato per procedere.")

        return pair.right_video, pair.left_video, Path(save_path)

    def _create_worker(self, model_path, target_label, stereo_config, source):
        right_video, left_video, output_path = source
        return VideoStereoAnalysisWorker(right_video, left_video, output_path, model_path, target_label, stereo_config)

    def _on_finished(self) -> None:
        super()._on_finished()
        if self.worker is not None and getattr(self.worker, "output_video_path", None):
            QMessageBox.information(
                self, "Analisi completata",
                f"Video annotato (camera sinistra) salvato in:\n{self.worker.output_video_path}",
            )
