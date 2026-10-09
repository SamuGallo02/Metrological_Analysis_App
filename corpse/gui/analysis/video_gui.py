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

import shutil
from pathlib import Path
from typing import List, Optional, Set, Union

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

from corpse.functions.analysis.analysis import ObjectAnalyzer, PairResult, render_overlay
from corpse.functions.analysis.pairing import find_single_video, is_stereo_dataset_folder
from corpse.functions.analysis.tracking import ObjectTracker, generate_adaptive_prefixes
from corpse.gui.analysis.analysis_page_base import AnalysisPageBase

from common.paths import VIDEO_DIR as DATASETS_VIDEO_DIR  # noqa: E402


def scan_video_datasets(root: Path = DATASETS_VIDEO_DIR) -> List[str]:
    if not root.is_dir():
        return []
    return sorted(f.name for f in root.iterdir() if f.is_dir())


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

                overlay = render_overlay(frame, detections)
                writer.write(overlay)

                result = PairResult(
                    timestamp=timestamp, right_image=frame, left_image=frame,
                    detections=detections, overlay_image=overlay,
                )
                self.pair_done.emit(result, tracker.total_count)
                if total_frames > 0:
                    self.progress.emit(frame_idx, total_frames)

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
        layout.addLayout(dataset_bar)

        note = QLabel("La cartella deve contenere UN SOLO file video (non rx/lx: quello è per la modalità Stereo).")
        note.setStyleSheet("color: #aaaaaa; font-style: italic;")
        layout.addWidget(note)

        self._refresh_datasets()

    def _add_dataset(self) -> None:
        DATASETS_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        source_dir = QFileDialog.getExistingDirectory(
            self, "Seleziona cartella con un video (non rx/lx)", str(DATASETS_VIDEO_DIR.resolve())
        )
        if not source_dir:
            return

        source = Path(source_dir)
        if is_stereo_dataset_folder(source):
            QMessageBox.critical(
                self, "Cartella non valida",
                f"'{source.name}' contiene le sottocartelle rx/lx: è un dataset per la modalità Video Stereo, "
                f"non per il Video Singolo. Selezionala nella modalità Stereo invece.",
            )
            return

        dest = DATASETS_VIDEO_DIR / source.name
        if dest.exists():
            reply = QMessageBox.question(
                self, "Cartella esistente", f"Una cartella denominata '{source.name}' esiste già. Sovrascrivere?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                shutil.rmtree(dest)
            except OSError as exc:
                QMessageBox.critical(self, "Errore rimozione", f"Impossibile sovrascrivere:\n{exc}")
                return

        try:
            shutil.copytree(source, dest)
        except OSError as exc:
            QMessageBox.critical(self, "Errore di copia", f"Impossibile copiare:\n{exc}")
            return

        self._refresh_datasets()
        self.folder_combo.setCurrentText(source.name)

    def _refresh_datasets(self) -> None:
        DATASETS_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        current = self.folder_combo.currentText()
        self.folder_combo.blockSignals(True)
        self.folder_combo.clear()

        datasets = scan_video_datasets()
        if not datasets:
            self.folder_combo.addItem("Nessuna cartella trovata in datasets/Dataset_Locale/dataset_Video/")
            self.folder_combo.setEnabled(False)
            self.selected_folder = None
        else:
            self.folder_combo.setEnabled(True)
            self.folder_combo.addItems(datasets)
            if current in datasets:
                self.folder_combo.setCurrentText(current)
            self.selected_folder = str(DATASETS_VIDEO_DIR / self.folder_combo.currentText())

        self.folder_combo.blockSignals(False)
        self._update_run_button_state()

    def _on_folder_selection_changed(self, _index: int) -> None:
        name = self.folder_combo.currentText()
        self.selected_folder = str(DATASETS_VIDEO_DIR / name) if name else None
        self._update_run_button_state()

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
