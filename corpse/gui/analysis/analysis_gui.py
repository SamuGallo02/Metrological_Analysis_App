"""
Graphical Interface Module for Stereo-Photogrammetric Metrological Analysis
(rx/lx photo pairs, with real length/width/distance measurements).

The TRAINING button has been removed from this page: training is
reached only from the home page, no longer as a shortcut from here.

Autore: Samuele Gallo
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Set

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from corpse.functions.analysis.analysis import ObjectAnalyzer, PairResult, StereoConfig, render_overlay
from corpse.functions.analysis.pairing import StereoPairFinder
from corpse.functions.analysis.label_export import LabelRecorder, model_class_names, save_media_labels
from corpse.functions.analysis.tracking import ObjectTracker, generate_adaptive_prefixes
from corpse.gui.analysis.analysis_page_base import AnalysisPageBase
from corpse.gui.analysis.library_picker import add_folder, on_selected, refresh, remove_selected


class StereoAnalysisWorker(QThread):
    """Analysis thread for stereo pairs of PHOTOS (rx/lx)."""
    progress = Signal(int, int)
    pair_done = Signal(object, int)
    finished_all = Signal()
    error = Signal(str)

    def __init__(self, folder: str, model_path: str, target_label=None, stereo_config: Optional[StereoConfig] = None) -> None:
        super().__init__()
        self.folder = folder
        self.model_path = model_path
        self.target_label = target_label
        self.stereo_config = stereo_config or StereoConfig()
        self._stop_requested = False

    def run(self) -> None:
        try:
            finder = StereoPairFinder(Path(self.folder))
            pairs = finder.scan_and_pair()

            if not pairs:
                self.error.emit("Nessuna coppia di fotogrammi stereo trovata nella directory.")
                return

            analyzer = ObjectAnalyzer(self.model_path, self.stereo_config)
            tracker = ObjectTracker()
            recorder = LabelRecorder(model_class_names(analyzer))
            seen_classes: Set[str] = set()

            for i, pair in enumerate(pairs, start=1):
                if self._stop_requested:
                    break

                result = analyzer.analyze_pair(
                    pair.timestamp, pair.right_path, pair.left_path, target_label=self.target_label
                )
                tracker.update(result.detections)

                for det in result.detections:
                    seen_classes.add(det.label)
                prefix_map = generate_adaptive_prefixes(list(seen_classes))

                for det in result.detections:
                    if det.track_id is not None:
                        prefix = prefix_map.get(det.label, "Obj")
                        str_id = str(det.track_id)
                        num_part = str_id.split("-")[-1].split("_")[-1]
                        det.track_id = f"{prefix}-{num_part}"

                left = result.left_image                       # the detection runs on the left camera: its photo gets the labels
                save_media_labels(pair.left_path, recorder.lines_for(result.detections, left.shape[1], left.shape[0]),
                                  recorder.classes)
                if self.stereo_config.detect_right:                                   # the right photo gets its labels too
                    right = result.right_image
                    save_media_labels(pair.right_path, recorder.lines_for(result.right_detections, right.shape[1],
                                                                          right.shape[0]), recorder.classes)
                result.overlay_image = render_overlay(result.left_image, result.detections)

                self.pair_done.emit(result, tracker.total_count)
                self.progress.emit(i, len(pairs))

            self.finished_all.emit()

        except Exception as exc:
            self.error.emit(str(exc))

    def stop(self) -> None:
        self._stop_requested = True


class StereoAnalysisPage(AnalysisPageBase):
    """Stereo-photogrammetric metrological analysis: rx/lx folders, real measurements."""

    def __init__(self, on_home, parent: Optional[object] = None) -> None:
        self.selected_folder: Optional[str] = None
        super().__init__(on_home, "Analisi Stereo", dual_preview=True, show_measurements=True, parent=parent)

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

        self._refresh_datasets()

    KIND = "photo_stereo"

    def _add_dataset(self) -> None:
        """Registers a folder where it is: nothing is copied into the application's folders."""
        add_folder(self, self.KIND, "Seleziona cartella con le acquisizioni stereo (rx/lx)",
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
            raise ValueError("Seleziona una cartella dataset valida (con sottocartelle rx/lx).")
        return self.selected_folder

    def _create_worker(self, model_path, target_label, stereo_config, source):
        return StereoAnalysisWorker(source, model_path, target_label, stereo_config)
