"""
Modulo dell'Interfaccia Grafica per l'Analisi di una Foto Singola.
Nessuna seconda camera disponibile: solo rilevamento YOLO (maschere, classe,
confidenza) — nessuna stima di dimensioni o distanza reale.

Autore: Samuele Gallo
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import cv2
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.analysis import ObjectDetection, analyze_single_image, render_overlay
from gui.analysis_gui import MODELS_DIR, scan_models


class SinglePhotoWorker(QThread):
    """Esegue il rilevamento su una singola immagine senza bloccare la GUI."""
    finished_signal = Signal(object, object)  # (image, detections)
    error_signal = Signal(str)

    def __init__(self, model_path: str, image_path: Path) -> None:
        super().__init__()
        self.model_path = model_path
        self.image_path = image_path

    def run(self) -> None:
        try:
            image, detections = analyze_single_image(self.model_path, self.image_path)
            self.finished_signal.emit(image, detections)
        except Exception as exc:
            self.error_signal.emit(str(exc))


class SinglePhotoPage(QWidget):
    """Pagina per il rilevamento di oggetti su una singola foto (senza stereo)."""

    def __init__(self, on_home, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.on_home = on_home
        self.worker: Optional[SinglePhotoWorker] = None
        self.image_path: Optional[Path] = None
        self.detections: List[ObjectDetection] = []

        self._build_ui()
        self._refresh_models()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        btn_back = QPushButton("← Torna alla home")
        btn_back.clicked.connect(self.on_home)
        top_bar.addWidget(btn_back)
        top_bar.addStretch(1)
        root_layout.addLayout(top_bar)

        root_layout.addWidget(QLabel("<h2>Analisi Foto Singola</h2>"))
        root_layout.addWidget(QLabel(
            "Rilevamento e segmentazione YOLO su una singola immagine: nessuna seconda "
            "camera disponibile, quindi nessuna stima di dimensioni o distanza reale — "
            "solo classe, maschera e confidenza."
        ))

        model_bar = QHBoxLayout()
        model_bar.addWidget(QLabel("Modello YOLO:"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(220)
        model_bar.addWidget(self.model_combo, stretch=1)
        btn_refresh_models = QPushButton("Aggiorna elenco")
        btn_refresh_models.clicked.connect(self._refresh_models)
        model_bar.addWidget(btn_refresh_models)
        root_layout.addLayout(model_bar)

        action_bar = QHBoxLayout()
        btn_load = QPushButton("Carica foto...")
        btn_load.clicked.connect(self._load_photo)
        action_bar.addWidget(btn_load)

        self.btn_run = QPushButton("AVVIA RILEVAMENTO")
        self.btn_run.setStyleSheet(
            "background-color: #2e7d32; color: white; font-weight: bold; padding: 6px;"
        )
        self.btn_run.setEnabled(False)
        self.btn_run.clicked.connect(self._run_detection)
        action_bar.addWidget(self.btn_run)
        action_bar.addStretch(1)
        root_layout.addLayout(action_bar)

        content_layout = QHBoxLayout()

        self.preview_label = QLabel("Nessuna foto caricata")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("background-color: #181818; color: #888888; border-radius: 4px;")
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_label.setMinimumHeight(400)
        content_layout.addWidget(self.preview_label, stretch=2)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Classe", "Confidenza", "Copertura (%)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMaximumWidth(400)
        content_layout.addWidget(self.table, stretch=1)

        root_layout.addLayout(content_layout, stretch=1)

    def _refresh_models(self) -> None:
        current = self.model_combo.currentText()
        self.model_combo.clear()
        models = scan_models()
        if not models:
            self.model_combo.addItem("Nessun modello trovato in models/")
            self.model_combo.setEnabled(False)
        else:
            self.model_combo.setEnabled(True)
            self.model_combo.addItems(models)
            if current in models:
                self.model_combo.setCurrentText(current)
        self._update_run_button_state()

    def _load_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona una foto", "", "Immagini (*.jpg *.jpeg *.png *.bmp *.tiff)"
        )
        if not path:
            return
        self.image_path = Path(path)
        self._render_preview_from_path(self.image_path)
        self._update_run_button_state()

    def _update_run_button_state(self) -> None:
        self.btn_run.setEnabled(self.image_path is not None and self.model_combo.isEnabled())

    def _run_detection(self) -> None:
        model_name = self.model_combo.currentText()
        if not model_name or not (MODELS_DIR / model_name).is_file():
            QMessageBox.warning(self, "Seleziona modello", "Selezionare un modello YOLO valido.")
            return
        if self.image_path is None:
            return

        model_path = str(MODELS_DIR / model_name)
        self.btn_run.setEnabled(False)

        self.worker = SinglePhotoWorker(model_path, self.image_path)
        self.worker.finished_signal.connect(self._on_detection_finished)
        self.worker.error_signal.connect(self._on_detection_error)
        self.worker.start()

    def _on_detection_finished(self, image, detections: List[ObjectDetection]) -> None:
        self.btn_run.setEnabled(True)
        self.detections = detections

        overlay = render_overlay(image, detections)
        self._render_preview_from_array(overlay)

        frame_area_px = image.shape[0] * image.shape[1] if image is not None else 0

        self.table.setRowCount(0)
        for det in detections:
            row = self.table.rowCount()
            self.table.insertRow(row)
            coverage_pct = (cv2.contourArea(det.contour) / frame_area_px * 100.0) if frame_area_px > 0 else 0.0
            self.table.setItem(row, 0, QTableWidgetItem(det.label))
            self.table.setItem(row, 1, QTableWidgetItem(f"{det.confidence:.2f}"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{coverage_pct:.2f}"))

        if not detections:
            QMessageBox.information(self, "Nessun rilevamento", "Nessun soggetto rilevato in questa foto.")

    def _on_detection_error(self, message: str) -> None:
        self.btn_run.setEnabled(True)
        QMessageBox.critical(self, "Errore di rilevamento", message)

    def _render_preview_from_path(self, path: Path) -> None:
        image = cv2.imread(str(path))
        if image is None:
            self.preview_label.setText("Impossibile leggere il file immagine.")
            return
        self._render_preview_from_array(image)

    def _render_preview_from_array(self, image) -> None:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)

        target_w = max(self.preview_label.width(), 100)
        target_h = max(self.preview_label.height(), 100)
        pixmap = QPixmap.fromImage(qimg).scaled(
            target_w, target_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(pixmap)
