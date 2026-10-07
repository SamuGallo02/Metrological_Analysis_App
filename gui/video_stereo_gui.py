"""
Modulo dell'Interfaccia Grafica per l'Analisi Video — modalita' Stereo (due
video sincronizzati, sx/dx). Identica in tutto e per tutto all'Analisi
Stereo su foto: stessa pipeline di misura reale (baseline + focale),
applicata frame per frame invece che a singole coppie di foto. Esporta
anche un video annotato (camera sinistra) con le maschere sovrimpresse.

Autore: Samuele Gallo
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Set, Union

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

from core.analysis import ObjectAnalyzer, PairResult, StereoConfig, render_overlay
from core.pairing import find_stereo_video_pair
from core.tracking import ObjectTracker, generate_adaptive_prefixes
from gui.analysis_page_base import AnalysisPageBase

DATASETS_VIDEO_STEREO_DIR = Path("Dataset_Video_Stereo")


def scan_video_stereo_datasets(root: Path = DATASETS_VIDEO_STEREO_DIR) -> List[str]:
    if not root.is_dir():
        return []
    return sorted(f.name for f in root.iterdir() if f.is_dir())


class VideoStereoAnalysisWorker(QThread):
    """Thread di analisi per una coppia di VIDEO sincronizzati (sx/dx), con misure reali."""
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

                result.overlay_image = render_overlay(result.left_image, result.detections)
                writer.write(result.overlay_image)

                self.pair_done.emit(result, tracker.total_count)
                if total_frames > 0:
                    self.progress.emit(frame_idx, total_frames)

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
    """Analisi Video — modalita' Stereo: due video sincronizzati (rx/lx), misure reali."""

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
        layout.addLayout(dataset_bar)

        note = QLabel("La cartella deve contenere le sottocartelle rx/ e lx/, ciascuna con un solo file video.")
        note.setStyleSheet("color: #aaaaaa; font-style: italic;")
        layout.addWidget(note)

        self._refresh_datasets()

    def _add_dataset(self) -> None:
        DATASETS_VIDEO_STEREO_DIR.mkdir(parents=True, exist_ok=True)
        source_dir = QFileDialog.getExistingDirectory(
            self, "Seleziona cartella con i due video sincronizzati (rx/lx)", str(DATASETS_VIDEO_STEREO_DIR.resolve())
        )
        if not source_dir:
            return

        import shutil
        source = Path(source_dir)
        dest = DATASETS_VIDEO_STEREO_DIR / source.name
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
        DATASETS_VIDEO_STEREO_DIR.mkdir(parents=True, exist_ok=True)
        current = self.folder_combo.currentText()
        self.folder_combo.blockSignals(True)
        self.folder_combo.clear()

        datasets = scan_video_stereo_datasets()
        if not datasets:
            self.folder_combo.addItem("Nessuna cartella trovata in Dataset_Video_Stereo/")
            self.folder_combo.setEnabled(False)
            self.selected_folder = None
        else:
            self.folder_combo.setEnabled(True)
            self.folder_combo.addItems(datasets)
            if current in datasets:
                self.folder_combo.setCurrentText(current)
            self.selected_folder = str(DATASETS_VIDEO_STEREO_DIR / self.folder_combo.currentText())

        self.folder_combo.blockSignals(False)
        self._update_run_button_state()

    def _on_folder_selection_changed(self, _index: int) -> None:
        name = self.folder_combo.currentText()
        self.selected_folder = str(DATASETS_VIDEO_STEREO_DIR / name) if name else None
        self._update_run_button_state()

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
