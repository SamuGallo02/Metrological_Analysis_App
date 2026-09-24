"""
Modulo dell'Interfaccia Grafica per l'Analisi Metrologica Stereo-Fotogrammetrica
(coppie di foto rx/lx, con misure di lunghezza/larghezza/distanza reali).

Il pulsante TRAINING e' stato rimosso da questa pagina: il training si
raggiunge solo dalla home, non piu' come scorciatoia da qui.

Autore: Samuele Gallo
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional, Set

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

from core.analysis import ObjectAnalyzer, PairResult, StereoConfig, render_overlay
from core.pairing import StereoPairFinder
from core.tracking import ObjectTracker, generate_adaptive_prefixes
from gui.analysis_page_base import AnalysisPageBase

DATASETS_DIR = Path("Dataset_Foto_Stereo")


def scan_datasets(datasets_dir: Path = DATASETS_DIR) -> List[str]:
    if not datasets_dir.is_dir():
        return []
    return sorted(f.name for f in datasets_dir.iterdir() if f.is_dir())


class StereoAnalysisWorker(QThread):
    """Thread di analisi per coppie stereo di FOTO (rx/lx)."""
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

                result.overlay_image = render_overlay(result.left_image, result.detections)

                self.pair_done.emit(result, tracker.total_count)
                self.progress.emit(i, len(pairs))

            self.finished_all.emit()

        except Exception as exc:
            self.error.emit(str(exc))

    def stop(self) -> None:
        self._stop_requested = True


class StereoAnalysisPage(AnalysisPageBase):
    """Analisi metrologica stereo-fotogrammetrica: cartelle rx/lx, misure reali."""

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
        layout.addLayout(dataset_bar)

        self._refresh_datasets()

    def _add_dataset(self) -> None:
        DATASETS_DIR.mkdir(parents=True, exist_ok=True)
        source_dir = QFileDialog.getExistingDirectory(
            self, "Seleziona cartella con le acquisizioni stereo (rx/lx)", str(DATASETS_DIR.resolve())
        )
        if not source_dir:
            return

        source = Path(source_dir)
        dest = DATASETS_DIR / source.name
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
        DATASETS_DIR.mkdir(parents=True, exist_ok=True)
        current = self.folder_combo.currentText()
        self.folder_combo.blockSignals(True)
        self.folder_combo.clear()

        datasets = scan_datasets()
        if not datasets:
            self.folder_combo.addItem("Nessuna cartella trovata in Dataset_Foto_Stereo/")
            self.folder_combo.setEnabled(False)
            self.selected_folder = None
        else:
            self.folder_combo.setEnabled(True)
            self.folder_combo.addItems(datasets)
            if current in datasets:
                self.folder_combo.setCurrentText(current)
            self.selected_folder = str(DATASETS_DIR / self.folder_combo.currentText())

        self.folder_combo.blockSignals(False)
        self._update_run_button_state()

    def _on_folder_selection_changed(self, _index: int) -> None:
        name = self.folder_combo.currentText()
        self.selected_folder = str(DATASETS_DIR / name) if name else None
        self._update_run_button_state()

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
