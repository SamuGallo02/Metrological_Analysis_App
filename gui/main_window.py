"""
Modulo dell'Interfaccia Grafica Principale
==========================================
Gestisce la finestra principale con selezione obbligatoria della classe oggetto.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List, Optional

import cv2
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.analysis import ObjectAnalyzer, PairResult, StereoConfig
from core.object_classes import add_class, load_classes, remove_class
from core.pairing import StereoPair, StereoPairFinder
from core.reporting import compute_summary, detections_to_dataframe, export_csv

MODELS_DIR = Path("models")
DATASETS_DIR = Path("datasets")


class ImagePreviewLabel(QLabel):
    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(100, 100)
        self._current_pixmap: Optional[QPixmap] = None

    def set_cv_image(self, cv_img: Optional[cv2.Mat]) -> None:
        if cv_img is None:
            self._current_pixmap = None
            self.setPixmap(QPixmap())
            self.setText("Immagine non disponibile")
            return

        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        self._current_pixmap = QPixmap.fromImage(qimg)
        self._update_scaled_pixmap()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self) -> None:
        if self._current_pixmap is not None and not self._current_pixmap.isNull():
            scaled = self._current_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            super().setPixmap(scaled)


def scan_models(models_dir: Path = MODELS_DIR) -> List[str]:
    if not models_dir.is_dir():
        return []
    return sorted(f.name for f in models_dir.iterdir() if f.suffix.lower() == ".pt")


def scan_datasets(datasets_dir: Path = DATASETS_DIR) -> List[str]:
    if not datasets_dir.is_dir():
        return []
    return sorted(f.name for f in datasets_dir.iterdir() if f.is_dir())


class AnalysisWorker(QThread):
    progress = Signal(int, int)
    pair_done = Signal(object)
    finished_all = Signal()
    error = Signal(str)

    def __init__(self, folder: str, model_path: str, target_label: str) -> None:
        super().__init__()
        self.folder = folder
        self.model_path = model_path
        self.target_label = target_label
        self._stop_requested = False

    def run(self) -> None:
        try:
            finder = StereoPairFinder(Path(self.folder))
            pairs = finder.scan_and_pair()

            if not pairs:
                self.error.emit("Nessuna coppia di fotogrammi stereo trovata nella directory.")
                return

            analyzer = ObjectAnalyzer(self.model_path, StereoConfig())

            for i, pair in enumerate(pairs, start=1):
                if self._stop_requested:
                    break

                result = analyzer.analyze_pair(
                    pair.timestamp, pair.right_path, pair.left_path, target_label=self.target_label
                )
                self.pair_done.emit(result)
                self.progress.emit(i, len(pairs))

            self.finished_all.emit()

        except Exception as exc:
            self.error.emit(str(exc))

    def stop(self) -> None:
        self._stop_requested = True


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("Stereo Metrology Analysis — YOLO")
        self.setMinimumSize(1280, 800)

        self.results: List[PairResult] = []
        self.available_pairs: Dict[str, StereoPair] = {}
        self.worker: Optional[AnalysisWorker] = None
        self.selected_folder: Optional[str] = None

        self._load_app_icon()
        self._build_ui()
        self._clear_gui_state()

    def _load_app_icon(self) -> None:
        base_dir = Path(__file__).parent.parent / "assets"
        icon_path = base_dir / "app_icon.ico"

        if not icon_path.exists():
            icon_path = base_dir / "app_icon.svg"

        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _build_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)

        # BARRA 1: DATASET
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Cartella dataset:"))

        self.folder_combo = QComboBox()
        self.folder_combo.setMinimumWidth(220)
        self.folder_combo.currentIndexChanged.connect(self._on_folder_selection_changed)
        top_bar.addWidget(self.folder_combo, stretch=1)

        btn_add_dataset = QPushButton("Aggiungi cartella...")
        btn_add_dataset.clicked.connect(self._add_dataset)
        top_bar.addWidget(btn_add_dataset)

        btn_refresh_datasets = QPushButton("Aggiorna elenco")
        btn_refresh_datasets.clicked.connect(self._refresh_datasets)
        top_bar.addWidget(btn_refresh_datasets)

        root_layout.addLayout(top_bar)

        # BARRA 2: MODELLI
        model_bar = QHBoxLayout()
        model_bar.addWidget(QLabel("Modello YOLO:"))

        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(220)
        model_bar.addWidget(self.model_combo)

        btn_add_model = QPushButton("Aggiungi modello...")
        btn_add_model.clicked.connect(self._add_model)
        model_bar.addWidget(btn_add_model)

        btn_refresh_models = QPushButton("Aggiorna elenco")
        btn_refresh_models.clicked.connect(self._refresh_models)
        model_bar.addWidget(btn_refresh_models)

        model_bar.addStretch(1)
        root_layout.addLayout(model_bar)

        # BARRA 3: OGGETTO DA ANALIZZARE (Senza opzione 'Tutti gli oggetti')
        class_bar = QHBoxLayout()
        class_bar.addWidget(QLabel("Oggetto da analizzare:"))

        self.class_combo = QComboBox()
        self.class_combo.setMinimumWidth(220)
        class_bar.addWidget(self.class_combo)

        btn_add_class = QPushButton("Aggiungi oggetto...")
        btn_add_class.clicked.connect(self._add_object_class)
        class_bar.addWidget(btn_add_class)

        btn_remove_class = QPushButton("Rimuovi oggetto")
        btn_remove_class.clicked.connect(self._remove_object_class)
        class_bar.addWidget(btn_remove_class)

        class_bar.addStretch(1)
        root_layout.addLayout(class_bar)

        # BARRA 4: AZIONI
        action_bar = QHBoxLayout()

        self.btn_run = QPushButton("Avvia analisi")
        self.btn_run.setEnabled(False)
        self.btn_run.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.btn_run.clicked.connect(self._run_analysis)

        self.btn_export = QPushButton("Esporta CSV")
        self.btn_export.setEnabled(False)
        self.btn_export.setStyleSheet("padding: 6px 14px;")
        self.btn_export.clicked.connect(self._export_csv)

        action_bar.addWidget(self.btn_run)
        action_bar.addWidget(self.btn_export)
        action_bar.addStretch(1)
        root_layout.addLayout(action_bar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        root_layout.addWidget(self.progress_bar)

        # PANNELLO CENTRALE
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.pair_list = QListWidget()
        self.pair_list.setMinimumWidth(160)
        self.pair_list.setMaximumWidth(220)
        self.pair_list.currentRowChanged.connect(self._show_pair_preview)
        splitter.addWidget(self.pair_list)

        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(5, 5, 5, 5)

        self.preview_title = QLabel("Visualizzazione Immagini Stereo")
        self.preview_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_title.setStyleSheet("font-weight: bold; margin-bottom: 6px;")
        preview_layout.addWidget(self.preview_title, stretch=0)

        images_layout = QHBoxLayout()
        images_layout.setSpacing(10)

        self.preview_left = ImagePreviewLabel("Camera Sinistra (LX) — Analisi & Maschera")
        self.preview_left.setStyleSheet("background-color: #1e1e1e; color: #888888; border: 1px solid #333;")

        self.preview_right = ImagePreviewLabel("Camera Destra (RX) — Originale Accoppiata")
        self.preview_right.setStyleSheet("background-color: #1e1e1e; color: #888888; border: 1px solid #333;")

        images_layout.addWidget(self.preview_left, stretch=1)
        images_layout.addWidget(self.preview_right, stretch=1)
        preview_layout.addLayout(images_layout, stretch=1)

        preview_container.setMinimumWidth(500)
        splitter.addWidget(preview_container)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        table_label = QLabel("Rilevamenti Metrologici")
        table_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        right_layout.addWidget(table_label)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            "Coppia", "Lunghezza (mm)", "Larghezza (mm)", "Confidenza"
        ])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.setStyleSheet("""
            QHeaderView::section {
                font-weight: bold;
                font-size: 11px;
                padding: 5px;
                background-color: #2b2b2b;
                color: #ffffff;
                border: 1px solid #3c3c3c;
            }
            QTableWidget {
                gridline-color: #3c3c3c;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 4px;
            }
        """)

        right_layout.addWidget(self.table, stretch=2)

        summary_label = QLabel("Statistiche Aggregate")
        summary_label.setStyleSheet("font-weight: bold; font-size: 13px; margin-top: 6px;")
        right_layout.addWidget(summary_label)

        self.summary_box = QTextEdit()
        self.summary_box.setReadOnly(True)
        self.summary_box.setStyleSheet("font-size: 11px;")
        right_layout.addWidget(self.summary_box, stretch=1)

        right_panel.setMinimumWidth(320)
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 12)
        splitter.setStretchFactor(1, 63)
        splitter.setStretchFactor(2, 25)

        root_layout.addWidget(splitter, stretch=1)

        self._refresh_object_classes()
        self._refresh_models()
        self._refresh_datasets()

    def _clear_gui_state(self) -> None:
        self.results.clear()
        self.table.setRowCount(0)
        self.summary_box.clear()
        self.btn_export.setEnabled(False)

        self.preview_left.set_cv_image(None)
        self.preview_right.set_cv_image(None)
        self.preview_left.setText("Camera Sinistra (LX) — Analisi & Maschera")
        self.preview_right.setText("Camera Destra (RX) — Originale Accoppiata")
        self.preview_title.setText("Visualizzazione Immagini Stereo")

    def _load_dataset_pairs(self) -> None:
        self.pair_list.clear()
        self.available_pairs.clear()

        if not self.selected_folder or not Path(self.selected_folder).exists():
            return

        try:
            finder = StereoPairFinder(Path(self.selected_folder))
            pairs = finder.scan_and_pair()
            for p in pairs:
                self.available_pairs[p.timestamp] = p
                self.pair_list.addItem(p.timestamp)
        except Exception:
            pass

    def _show_pair_preview(self, row: int) -> None:
        if row < 0 or row >= self.pair_list.count():
            return

        ts_item = self.pair_list.item(row)
        if not ts_item:
            return

        timestamp = ts_item.text().split(" ")[0]
        analysed_result = next((r for r in self.results if r.timestamp == timestamp), None)

        if analysed_result:
            self.preview_left.set_cv_image(analysed_result.mask_overlay_left)
            self.preview_right.set_cv_image(analysed_result.right_image)
            self.preview_title.setText(f"Coppia {timestamp} — Analisi completata")
        elif timestamp in self.available_pairs:
            pair = self.available_pairs[timestamp]
            img_l = cv2.imread(str(pair.left_path))
            img_r = cv2.imread(str(pair.right_path))
            self.preview_left.set_cv_image(img_l)
            self.preview_right.set_cv_image(img_r)
            self.preview_title.setText(f"Coppia {timestamp} — Fotogrammi Originali (LX / RX)")

    def _refresh_object_classes(self) -> None:
        current = self.class_combo.currentText()
        self.class_combo.blockSignals(True)
        self.class_combo.clear()

        # Carica solo la lista delle classi senza aggiungere 'Tutti gli oggetti'
        classes = load_classes()
        self.class_combo.addItems(classes)

        index = self.class_combo.findText(current)
        self.class_combo.setCurrentIndex(index if index >= 0 else 0)
        self.class_combo.blockSignals(False)

    def _add_object_class(self) -> None:
        name, ok = QInputDialog.getText(self, "Aggiungi oggetto", "Nome della classe YOLO:")
        if ok and name.strip():
            add_class(name)
            self._refresh_object_classes()
            self.class_combo.setCurrentText(name.strip())

    def _remove_object_class(self) -> None:
        if self.class_combo.count() > 0:
            name = self.class_combo.currentText()
            remove_class(name)
            self._refresh_object_classes()

    def _add_model(self) -> None:
        source_path, _ = QFileDialog.getOpenFileName(self, "Seleziona modello YOLO (.pt)", "", "Modelli YOLO (*.pt)")
        if source_path:
            source = Path(source_path)
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, MODELS_DIR / source.name)
            self._refresh_models()
            self.model_combo.setCurrentText(source.name)

    def _refresh_models(self) -> None:
        current = self.model_combo.currentText()
        self.model_combo.clear()
        models = scan_models()
        if models:
            self.model_combo.setEnabled(True)
            self.model_combo.addItems(models)
            if current in models:
                self.model_combo.setCurrentText(current)
        else:
            self.model_combo.addItem("Nessun modello trovato in models/")
            self.model_combo.setEnabled(False)
        self._update_run_button_state()

    def _add_dataset(self) -> None:
        source_dir = QFileDialog.getExistingDirectory(self, "Seleziona cartella con acquisizioni stereo")
        if source_dir:
            source = Path(source_dir)
            DATASETS_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, DATASETS_DIR / source.name, dirs_exist_ok=True)
            self._refresh_datasets()
            self.folder_combo.setCurrentText(source.name)

    def _refresh_datasets(self) -> None:
        current = self.folder_combo.currentText()
        self.folder_combo.blockSignals(True)
        self.folder_combo.clear()
        datasets = scan_datasets()
        if not datasets:
            self.folder_combo.addItem("Nessuna cartella trovata in datasets/")
            self.folder_combo.setEnabled(False)
            self.selected_folder = None
        else:
            self.folder_combo.setEnabled(True)
            self.folder_combo.addItems(datasets)
            if current in datasets:
                self.folder_combo.setCurrentText(current)
            self.selected_folder = str(DATASETS_DIR / self.folder_combo.currentText())

        self.folder_combo.blockSignals(False)
        self._load_dataset_pairs()
        self._update_run_button_state()

    def _on_folder_selection_changed(self, _index: int) -> None:
        name = self.folder_combo.currentText()
        self.selected_folder = str(DATASETS_DIR / name) if name else None
        self._load_dataset_pairs()
        self._update_run_button_state()

    def _update_run_button_state(self) -> None:
        self.btn_run.setEnabled(
            bool(self.selected_folder)
            and self.model_combo.isEnabled()
            and self.class_combo.count() > 0
        )

    def _run_analysis(self) -> None:
        model_name = self.model_combo.currentText()
        if not model_name or not (MODELS_DIR / model_name).is_file():
            QMessageBox.warning(self, "Seleziona modello", "Selezionare un modello YOLO valido.")
            return

        target_label = self.class_combo.currentText().strip()
        if not target_label:
            QMessageBox.warning(self, "Seleziona oggetto", "Selezionare una classe oggetto valida.")
            return

        model_path = str(MODELS_DIR / model_name)

        self._clear_gui_state()

        self.btn_run.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.worker = AnalysisWorker(self.selected_folder, model_path, target_label)
        self.worker.progress.connect(self._on_progress)
        self.worker.pair_done.connect(self._on_pair_done)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_progress(self, current: int, total: int) -> None:
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def _on_pair_done(self, result: PairResult) -> None:
        self.results.append(result)

        for det in result.detections:
            row = self.table.rowCount()
            self.table.insertRow(row)

            item_ts = QTableWidgetItem(result.timestamp)
            item_len = QTableWidgetItem(f"{det.length_mm:.1f}")
            item_wid = QTableWidgetItem(f"{det.width_mm:.1f}")
            item_conf = QTableWidgetItem(f"{det.confidence:.2f}")

            for item in (item_ts, item_len, item_wid, item_conf):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setItem(row, 0, item_ts)
            self.table.setItem(row, 1, item_len)
            self.table.setItem(row, 2, item_wid)
            self.table.setItem(row, 3, item_conf)

        current_row = self.pair_list.currentRow()
        if current_row >= 0:
            self._show_pair_preview(current_row)

    def _on_finished(self) -> None:
        self.progress_bar.setVisible(False)
        self.btn_run.setEnabled(True)
        self.btn_export.setEnabled(bool(self.results))
        self._update_summary()

        if self.pair_list.count() > 0 and self.pair_list.currentRow() < 0:
            self.pair_list.setCurrentRow(0)

    def _on_error(self, message: str) -> None:
        self.progress_bar.setVisible(False)
        self.btn_run.setEnabled(True)
        QMessageBox.critical(self, "Errore di analisi", message)

    def _update_summary(self) -> None:
        try:
            df = detections_to_dataframe(self.results)
            summary = compute_summary(df)
            if hasattr(summary, "to_string"):
                self.summary_box.setText(summary.to_string(index=False) if not summary.empty else "Nessun rilevamento.")
        except Exception as exc:
            self.summary_box.setText(f"Errore nel calcolo delle statistiche: {exc}")

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Esporta report CSV", "risultati_metrologia.csv", "CSV (*.csv)")
        if path:
            try:
                df = detections_to_dataframe(self.results)
                export_csv(df, path)
                QMessageBox.information(self, "Esportazione completata", f"File salvato in:\n{path}")
            except Exception as exc:
                QMessageBox.critical(self, "Errore esportazione", f"Impossibile esportare il CSV:\n{exc}")