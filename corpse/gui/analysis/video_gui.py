"""
Graphical Interface Module for Video Analysis — Single mode (a
single video file, not stereo). Identical in every respect to Stereo
Analysis EXCEPT the measurements: no second camera, hence no estimate of
real dimensions or distance. In addition to the other pages: it also
exports an annotated video with the masks overlaid.

Source selection follows the same "dataset folder +
Add folder" scheme as the other three pages: each subfolder of
Dataset_Video/ must contain exactly ONE video file (not an rx/lx pair,
reserved for Stereo mode).

Autore: Samuele Gallo
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Set, Union

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

from corpse.functions.analysis.analysis import ObjectAnalyzer, PairResult, render_overlay
from corpse.functions.analysis.pairing import find_single_video, is_stereo_dataset_folder
from corpse.functions.analysis.label_export import LabelRecorder, model_class_names, save_media_labels
from corpse.functions.analysis.tracking import ObjectTracker, generate_adaptive_prefixes
from corpse.gui.analysis.analysis_page_base import AnalysisPageBase
from corpse.gui.analysis.library_picker import add_folder, on_selected, refresh, remove_selected


class VideoAnalysisWorker(QThread):
    """Analysis thread for a SINGLE VIDEO (not stereo): detection + frame-by-frame tracking."""
    progress = Signal(int, int)
    pair_done = Signal(object, int)
    finished_all = Signal()
    error = Signal(str)

    def __init__(
            self, video_path: Path, output_video_path: Path, model_path: str,
            target_label: Optional[Union[str, List[str]]] = None,
    ) -> None:
        super().__init__()
        self.video_path = video_path
        self.output_video_path = output_video_path
        self.model_path = model_path
        self.target_label = target_label
        self._stop_requested = False

    def run(self) -> None:
        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            self.error.emit(f"Impossibile aprire il file video: {self.video_path}")
            return

        writer = None
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(self.output_video_path), fourcc, fps, (width, height))

            analyzer = ObjectAnalyzer(self.model_path)
            tracker = ObjectTracker()
            recorder = LabelRecorder(model_class_names(analyzer))
            label_lines: List[str] = []                              # `frame cls ...` for the whole video
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

                ok, frame = cap.read()
                if not ok:
                    break

                frame_idx += 1
                timestamp = f"frame_{frame_idx:06d}"

                detections = analyzer.detect_in_image(frame, timestamp=timestamp)
                if target_labels_lower is not None:
                    detections = [d for d in detections if d.label.strip().lower() in target_labels_lower]

                tracker.update(detections)
                for det in detections:
                    seen_classes.add(det.label)
                prefix_map = generate_adaptive_prefixes(list(seen_classes))
                for det in detections:
                    if det.track_id is not None:
                        prefix = prefix_map.get(det.label, "Obj")
                        num_part = str(det.track_id).split("-")[-1].split("_")[-1]
                        det.track_id = f"{prefix}-{num_part}"

                label_lines.extend(recorder.lines_for(detections, frame.shape[1], frame.shape[0], frame_idx))
                overlay = render_overlay(frame, detections)
                writer.write(overlay)

                result = PairResult(
                    timestamp=timestamp, right_image=frame, left_image=frame,
                    detections=detections, overlay_image=overlay,
                )
                self.pair_done.emit(result, tracker.total_count)
                if total_frames > 0:
                    self.progress.emit(frame_idx, total_frames)

            save_media_labels(self.video_path, label_lines, recorder.classes)
            self.finished_all.emit()

        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            cap.release()
            if writer is not None:
                writer.release()

    def stop(self) -> None:
        self._stop_requested = True


class VideoAnalysisPage(AnalysisPageBase):
    """Video Analysis — Single mode: folder with one video, no measurements, exports annotated video."""

    def __init__(self, on_home, parent: Optional[object] = None) -> None:
        self.selected_folder: Optional[str] = None
        super().__init__(on_home, "Analisi Video — Singolo", dual_preview=False, show_measurements=False, parent=parent)

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

        note = QLabel("La cartella deve contenere UN SOLO file video (non rx/lx: quello è per la modalità Stereo).")
        note.setStyleSheet("color: #aaaaaa; font-style: italic;")
        layout.addWidget(note)

        self._refresh_datasets()

    KIND = "video"

    @staticmethod
    def _validate_folder(folder: Path):
        if is_stereo_dataset_folder(folder):
            return (f"'{folder.name}' contiene le sottocartelle rx/lx: e' un dataset per la modalita' Video Stereo, "
                    f"non per il Video Singolo. Selezionala nella modalita' Stereo invece.")
        return None

    def _add_dataset(self) -> None:
        """Registers a folder where it is: nothing is copied into the application's folders."""
        add_folder(self, self.KIND, "Seleziona cartella con un video (non rx/lx)",
                   self._validate_folder)

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
            raise ValueError("Seleziona una cartella dataset valida (con un solo file video).")

        video_path = find_single_video(Path(self.selected_folder))

        save_path, _ = QFileDialog.getSaveFileName(
            self, "Salva video annotato come",
            str(video_path.with_name(video_path.stem + "_annotato.mp4")),
            "Video MP4 (*.mp4)",
        )
        if not save_path:
            raise ValueError("Esportazione annullata: scegli dove salvare il video annotato per procedere.")

        return video_path, Path(save_path)

    def _create_worker(self, model_path, target_label, stereo_config, source):
        video_path, output_path = source
        return VideoAnalysisWorker(video_path, output_path, model_path, target_label)

    def _on_finished(self) -> None:
        super()._on_finished()
        if self.worker is not None and getattr(self.worker, "output_video_path", None):
            QMessageBox.information(
                self, "Analisi completata",
                f"Video annotato salvato in:\n{self.worker.output_video_path}",
            )
