"""
Demo Webcam: dialogo di configurazione (modello, classe, camera/e) e pulsante che avvia
tools/webcam_demo.py in un processo separato. Il pulsante vive nella schermata Analisi.

Autore: Samuele Gallo
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from common.i18n import tr
from core.analysis import list_model_classes
from core.camera_utils import list_available_cameras
from gui.analysis_page_base import MODELS_DIR, scan_models

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODE_MONO, MODE_STEREO = "mono", "stereo"        # valori interni (non tradotti)


class WebcamDemoDialog(QDialog):
    """
    Sceglie quale modello YOLO usare, cosa riconoscere e con quale/i camera/e lavorare. Le classi sono
    lette DAL MODELLO SCELTO; le camere sono rilevate collegandosi davvero a ciascuna: con almeno due
    camere la modalita' "Stereo dal vivo" e' selezionabile (misure reali dal vivo, come nell'Analisi
    Video Stereo).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Webcam demo — settings"))
        self.resize(400, 260)
        self.selected_model_path: str | None = None
        self.selected_class: str | None = None  # None = tutti gli oggetti
        self.selected_mode: str = MODE_MONO
        self.selected_camera: int = 0
        self.selected_camera_left: int = 0
        self.selected_camera_right: int = 1

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("YOLO model:")))
        self.combo_model = QComboBox()
        self.combo_model.currentIndexChanged.connect(self._refresh_classes)
        layout.addWidget(self.combo_model)

        layout.addWidget(QLabel(tr("What to recognise:")))
        self.combo_class = QComboBox()
        layout.addWidget(self.combo_class)

        layout.addWidget(QLabel(tr("Mode:")))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem(tr("Single camera"), MODE_MONO)
        self.combo_mode.addItem(tr("Live stereo (2 cameras)"), MODE_STEREO)
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        layout.addWidget(self.combo_mode)

        self.lbl_cameras_status = QLabel(tr("Looking for available cameras..."))
        self.lbl_cameras_status.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(self.lbl_cameras_status)

        self.row_mono = QWidget()
        row_mono_layout = QHBoxLayout(self.row_mono)
        row_mono_layout.setContentsMargins(0, 0, 0, 0)
        row_mono_layout.addWidget(QLabel(tr("Camera:")))
        self.combo_camera = QComboBox()
        row_mono_layout.addWidget(self.combo_camera)
        layout.addWidget(self.row_mono)

        self.row_stereo = QWidget()
        row_stereo_layout = QHBoxLayout(self.row_stereo)
        row_stereo_layout.setContentsMargins(0, 0, 0, 0)
        row_stereo_layout.addWidget(QLabel(tr("Left (L):")))
        self.combo_camera_left = QComboBox()
        row_stereo_layout.addWidget(self.combo_camera_left)
        row_stereo_layout.addWidget(QLabel(tr("Right (R):")))
        self.combo_camera_right = QComboBox()
        row_stereo_layout.addWidget(self.combo_camera_right)
        layout.addWidget(self.row_stereo)
        self.row_stereo.setVisible(False)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_cancel = QPushButton(tr("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        self.btn_start = QPushButton(tr("Start"))
        self.btn_start.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 5px 14px;")
        self.btn_start.clicked.connect(self._on_start)
        btn_row.addWidget(self.btn_start)
        layout.addLayout(btn_row)

        self._populate_models()
        self._populate_cameras()

    def _populate_models(self) -> None:
        models = scan_models()
        self.combo_model.clear()
        if not models:
            self.combo_model.addItem(tr("No model found in models/"))
            self.combo_model.setEnabled(False)
        else:
            self.combo_model.setEnabled(True)
            self.combo_model.addItems(models)
        self._refresh_classes()

    def _refresh_classes(self) -> None:
        self.combo_class.clear()
        self.combo_class.addItem(tr("All objects"), None)
        model_path = MODELS_DIR / self.combo_model.currentText()
        if model_path.is_file():
            try:
                for name in list_model_classes(str(model_path)):
                    self.combo_class.addItem(name, name)
            except Exception:
                pass  # se la lettura fallisce resta disponibile "Tutti gli oggetti"
        idx = self.combo_class.findData("person")      # preseleziona "person" quando presente
        if idx >= 0:
            self.combo_class.setCurrentIndex(idx)

    def _populate_cameras(self) -> None:
        """Individua le camere realmente disponibili (una sola volta, all'apertura del dialogo)."""
        cameras = list_available_cameras(max_index=6)
        self.combo_camera.clear()
        self.combo_camera_left.clear()
        self.combo_camera_right.clear()

        if not cameras:
            self.lbl_cameras_status.setText(tr("No camera found. Connect a webcam (built-in or USB) and reopen this window."))
            self.combo_camera.addItem(tr("No camera found"))
            self.combo_camera.setEnabled(False)
            self.combo_mode.model().item(1).setEnabled(False)
            self.btn_start.setEnabled(False)
            return

        self.lbl_cameras_status.setText(tr("Cameras found: {list}", list=", ".join(str(c) for c in cameras)))
        for cam in cameras:
            label = tr("Camera {n}", n=cam)
            self.combo_camera.addItem(label, cam)
            self.combo_camera_left.addItem(label, cam)
            self.combo_camera_right.addItem(label, cam)

        if len(cameras) >= 2:
            self.combo_camera_right.setCurrentIndex(1)
        else:
            self.combo_mode.model().item(1).setEnabled(False)
            self.lbl_cameras_status.setText(
                tr("Cameras found: {list}", list=", ".join(str(c) for c in cameras))
                + " — " + tr("a second camera is needed for stereo mode."))

    def _on_mode_changed(self) -> None:
        is_stereo = self.combo_mode.currentData() == MODE_STEREO
        self.row_mono.setVisible(not is_stereo)
        self.row_stereo.setVisible(is_stereo)

    def _on_start(self) -> None:
        model_path = MODELS_DIR / self.combo_model.currentText()
        if not model_path.is_file():
            QMessageBox.warning(self, tr("No model"), tr("Select a valid YOLO model."))
            return
        self.selected_model_path = str(model_path)
        self.selected_class = self.combo_class.currentData()

        if self.combo_mode.currentData() == MODE_STEREO:
            cam_left, cam_right = self.combo_camera_left.currentData(), self.combo_camera_right.currentData()
            if cam_left is None or cam_right is None:
                QMessageBox.warning(self, tr("Cameras not available"), tr("Select two valid cameras."))
                return
            if cam_left == cam_right:
                QMessageBox.warning(self, tr("Identical cameras"), tr("The left and right cameras must be two different devices."))
                return
            self.selected_mode, self.selected_camera_left, self.selected_camera_right = MODE_STEREO, cam_left, cam_right
        else:
            cam = self.combo_camera.currentData()
            if cam is None:
                QMessageBox.warning(self, tr("Camera not available"), tr("Select a valid camera."))
                return
            self.selected_mode, self.selected_camera = MODE_MONO, cam
        self.accept()


class WebcamDemoButton(QPushButton):
    """
    Avvia tools/webcam_demo.py come processo indipendente (non bloccante): l'app resta utilizzabile.
    Il pulsante si disabilita come PRIMA istruzione del clic, cosi' un secondo clic ravvicinato non puo'
    rientrare nella funzione; torna attivo quando l'esito e' noto (annullato, errore) o quando il
    processo della demo termina (controllato da un QTimer, senza bloccare l'interfaccia).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(tr("🎥 Webcam demo"), parent)
        self.setToolTip(tr("Starts live YOLO detection from the webcam in a separate window."))
        self._process = None
        self._watchdog: QTimer | None = None
        self.clicked.connect(self._launch)

    def _launch(self) -> None:
        self.setEnabled(False)
        try:
            if self._process is not None and self._process.poll() is None:
                QMessageBox.information(
                    self, tr("Demo already open"),
                    tr("The webcam demo is already running: look for it among the open windows (it may be behind "
                       "this one), or close it before opening another."))
                return

            script_path = PROJECT_ROOT / "tools" / "webcam_demo.py"
            if not script_path.is_file():
                QMessageBox.critical(self, tr("Demo not found"), tr("File not found:\n{path}", path=script_path))
                return
            if not MODELS_DIR.is_dir() or not any(MODELS_DIR.glob("*.pt")):
                QMessageBox.warning(self, tr("No model available"),
                                    tr("Put at least one YOLO model (.pt) in the models/ folder before starting the demo."))
                return

            dialog = WebcamDemoDialog(self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            args = [sys.executable, str(script_path), "--model", dialog.selected_model_path,
                    "--class", dialog.selected_class if dialog.selected_class is not None else "all"]
            if dialog.selected_mode == MODE_STEREO:
                args += ["--mode", "stereo", "--camera-left", str(dialog.selected_camera_left),
                         "--camera-right", str(dialog.selected_camera_right)]
            else:
                args += ["--camera", str(dialog.selected_camera)]
            try:
                self._process = subprocess.Popen(args, cwd=str(PROJECT_ROOT))
            except Exception as exc:
                QMessageBox.critical(self, tr("Error starting the demo"), tr("Could not start the demo:\n{error}", error=exc))
                return
            self._start_watchdog()
        finally:
            if not (self._process is not None and self._process.poll() is None):
                self.setEnabled(True)

    def _start_watchdog(self) -> None:
        if self._watchdog is not None:
            self._watchdog.stop()
        timer = QTimer(self)
        timer.setInterval(1000)
        timer.timeout.connect(self._check_process)
        timer.start()
        self._watchdog = timer

    def _check_process(self) -> None:
        if self._process is None or self._process.poll() is not None:
            if self._watchdog is not None:
                self._watchdog.stop()
                self._watchdog = None
            self.setEnabled(True)
