"""
Graphical Interface Module for Photo Analysis (folder of single photos).
Identical in every respect to Stereo Analysis EXCEPT the measurements: no
second camera available, hence no estimate of real dimensions or distance
— only class, mask and confidence.

Autore: Samuele Gallo
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Set, Union

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from corpse.functions.analysis.analysis import ObjectAnalyzer, PairResult, render_overlay
from corpse.functions.analysis.pairing import SingleImageFinder, is_stereo_dataset_folder
from corpse.functions.analysis.label_export import LabelRecorder, model_class_names, save_media_labels
from corpse.functions.analysis.tracking import ObjectTracker, generate_adaptive_prefixes
from corpse.gui.analysis.analysis_page_base import AnalysisPageBase
from corpse.gui.analysis.library_picker import add_folder, on_selected, refresh, remove_selected


class PhotoAnalysisWorker(QThread):
    """Analysis thread for a folder of SINGLE PHOTOS (no stereo pair)."""
    progress = Signal(int, int)
    pair_done = Signal(object, int)
    finished_all = Signal()
    error = Signal(str)

    def __init__(self, folder: str, model_path: str, target_label: Optional[Union[str, List[str]]] = None) -> None:
        super().__init__()
        self.folder = folder
        self.model_path = model_path
        self.target_label = target_label
        self._stop_requested = False

    def run(self) -> None:
        try:
            finder = SingleImageFinder(Path(self.folder))
            items = finder.scan()

            if not items:
                self.error.emit("Nessuna foto trovata nella cartella selezionata.")
                return

            analyzer = ObjectAnalyzer(self.model_path)
            tracker = ObjectTracker()
            recorder = LabelRecorder(model_class_names(analyzer))     # labels stay associated with each photo
            seen_classes: Set[str] = set()

            target_labels_lower = None
            if isinstance(self.target_label, str):
                target_labels_lower = {self.target_label.strip().lower()}
            elif isinstance(self.target_label, list):
                target_labels_lower = {t.strip().lower() for t in self.target_label}

            for i, item in enumerate(items, start=1):
                if self._stop_requested:
                    break

                image = cv2.imread(str(item.image_path))
                if image is None:
                    continue

                detections = analyzer.detect_in_image(image, timestamp=item.timestamp)
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

                save_media_labels(item.image_path, recorder.lines_for(detections, image.shape[1], image.shape[0]),
                                  recorder.classes)
                overlay = render_overlay(image, detections)
                result = PairResult(
                    timestamp=item.timestamp, right_image=image, left_image=image,
                    detections=detections, overlay_image=overlay,
                )

                self.pair_done.emit(result, tracker.total_count)
                self.progress.emit(i, len(items))

            self.finished_all.emit()

        except Exception as exc:
            self.error.emit(str(exc))

    def stop(self) -> None:
        self._stop_requested = True


class PhotoAnalysisPage(AnalysisPageBase):
    """Photo Analysis: folder of single photos, detection only (no measurements)."""

    def __init__(self, on_home, parent: Optional[object] = None) -> None:
        self.selected_folder: Optional[str] = None
        super().__init__(on_home, "Analisi Foto", dual_preview=False, show_measurements=False, parent=parent)

    def _build_source_selector_ui(self, layout: QVBoxLayout) -> None:
        dataset_bar = QHBoxLayout()
        lbl_dataset = QLabel("Cartella foto:")
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

    KIND = "photo"

    @staticmethod
    def _validate_folder(folder: Path):
        if is_stereo_dataset_folder(folder):
            return (f"'{folder.name}' contiene le sottocartelle rx/lx: e' un dataset per l'Analisi Stereo, "
                    f"non per l'Analisi Foto. Selezionala nella pagina Analisi Stereo invece.")
        return None

    def _add_dataset(self) -> None:
        """Registers a folder where it is: nothing is copied into the application's folders."""
        add_folder(self, self.KIND, "Seleziona cartella con foto singole (non rx/lx)",
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
            raise ValueError("Seleziona una cartella foto valida.")
        return self.selected_folder

    def _create_worker(self, model_path, target_label, stereo_config, source):
        return PhotoAnalysisWorker(source, model_path, target_label)
