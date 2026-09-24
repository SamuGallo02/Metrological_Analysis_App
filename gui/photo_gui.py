"""
Modulo dell'Interfaccia Grafica per l'Analisi Foto (cartella di foto singole).
Identica in tutto e per tutto all'Analisi Stereo TRANNE le misure: nessuna
seconda camera disponibile, quindi nessuna stima di dimensioni o distanza
reale — solo classe, maschera e confidenza.

Autore: Samuele Gallo
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional, Set, Union

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

from core.analysis import ObjectAnalyzer, PairResult, render_overlay
from core.pairing import SingleImageFinder, is_stereo_dataset_folder
from core.tracking import ObjectTracker, generate_adaptive_prefixes
from gui.analysis_page_base import AnalysisPageBase

DATASETS_FOTO_DIR = Path("Dataset_Foto")


def scan_foto_datasets(root: Path = DATASETS_FOTO_DIR) -> List[str]:
    if not root.is_dir():
        return []
    return sorted(f.name for f in root.iterdir() if f.is_dir())


class PhotoAnalysisWorker(QThread):
    """Thread di analisi per una cartella di FOTO SINGOLE (nessuna coppia stereo)."""
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
    """Analisi Foto: cartella di foto singole, solo rilevamento (nessuna misura)."""

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
        layout.addLayout(dataset_bar)

        self._refresh_datasets()

    def _add_dataset(self) -> None:
        DATASETS_FOTO_DIR.mkdir(parents=True, exist_ok=True)
        source_dir = QFileDialog.getExistingDirectory(
            self, "Seleziona cartella con foto singole (non rx/lx)", str(DATASETS_FOTO_DIR.resolve())
        )
        if not source_dir:
            return

        source = Path(source_dir)
        if is_stereo_dataset_folder(source):
            QMessageBox.critical(
                self, "Cartella non valida",
                f"'{source.name}' contiene le sottocartelle rx/lx: è un dataset per l'Analisi Stereo, "
                f"non per l'Analisi Foto. Selezionala nella pagina Analisi Stereo invece.",
            )
            return

        dest = DATASETS_FOTO_DIR / source.name
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
        DATASETS_FOTO_DIR.mkdir(parents=True, exist_ok=True)
        current = self.folder_combo.currentText()
        self.folder_combo.blockSignals(True)
        self.folder_combo.clear()

        datasets = scan_foto_datasets()
        if not datasets:
            self.folder_combo.addItem("Nessuna cartella trovata in Dataset_Foto/")
            self.folder_combo.setEnabled(False)
            self.selected_folder = None
        else:
            self.folder_combo.setEnabled(True)
            self.folder_combo.addItems(datasets)
            if current in datasets:
                self.folder_combo.setCurrentText(current)
            self.selected_folder = str(DATASETS_FOTO_DIR / self.folder_combo.currentText())

        self.folder_combo.blockSignals(False)
        self._update_run_button_state()

    def _on_folder_selection_changed(self, _index: int) -> None:
        name = self.folder_combo.currentText()
        self.selected_folder = str(DATASETS_FOTO_DIR / name) if name else None
        self._update_run_button_state()

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
