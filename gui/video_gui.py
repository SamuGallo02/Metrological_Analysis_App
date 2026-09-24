"""
Modulo dell'Interfaccia Grafica per l'Analisi Video (monoculare, non stereo).
Rilevamento + tracciamento multi-frame come nell'analisi stereo (conteggio
cumulativo di individui distinti), senza alcuna stima di dimensioni/distanza
reale (nessuna seconda camera). Esporta un video annotato con le maschere
sovrimpresse e, opzionalmente, un CSV dei rilevamenti.

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
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.analysis import ObjectAnalyzer, PairResult, render_overlay
from core.reporting import detections_to_dataframe, export_csv
from core.tracking import ObjectTracker
from gui.analysis_gui import MODELS_DIR, generate_adaptive_prefixes, scan_models


class VideoAnalysisWorker(QThread):
    """
    Esegue rilevamento + tracciamento frame-per-frame su un video, scrivendo
    un video annotato in output e accumulando i rilevamenti per l'export CSV.
    """
    progress = Signal(int, int)
    preview_frame = Signal(object)
    finished_all = Signal(int, str, object)  # (conteggio cumulativo, path video, lista PairResult)
    error = Signal(str)

    def __init__(self, model_path: str, video_path: Path, output_path: Path) -> None:
        super().__init__()
        self.model_path = model_path
        self.video_path = video_path
        self.output_path = output_path
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            self.error.emit(f"Impossibile aprire il file video: {self.video_path}")
            return

        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(self.output_path), fourcc, fps, (width, height))

            analyzer = ObjectAnalyzer(self.model_path)
            tracker = ObjectTracker()
            seen_classes = set()
            results: List[PairResult] = []

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

                pair_result = PairResult(timestamp=timestamp, right_image=frame, left_image=frame,
                                          detections=detections, overlay_image=overlay)
                results.append(pair_result)

                if frame_idx % 5 == 0 or frame_idx == 1:
                    self.preview_frame.emit(overlay)
                if total_frames > 0:
                    self.progress.emit(frame_idx, total_frames)

            writer.release()
            self.finished_all.emit(tracker.total_count, str(self.output_path), results)

        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            cap.release()


class VideoPage(QWidget):
    """Pagina per l'analisi di un video singolo (non stereo)."""

    def __init__(self, on_home, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.on_home = on_home
        self.worker: Optional[VideoAnalysisWorker] = None
        self.video_path: Optional[Path] = None
        self.output_path: Optional[Path] = None
        self.results: List[PairResult] = []

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

        root_layout.addWidget(QLabel("<h2>Analisi Video</h2>"))
        root_layout.addWidget(QLabel(
            "Rilevamento e tracciamento multi-frame su un video singolo (non stereo): "
            "conteggio cumulativo di individui distinti come nell'analisi stereo, ma "
            "senza stima di dimensioni/distanza reale. Esporta un video annotato con "
            "le maschere sovrimpresse."
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
        btn_load = QPushButton("Carica video...")
        btn_load.clicked.connect(self._load_video)
        action_bar.addWidget(btn_load)

        self.btn_run = QPushButton("AVVIA ANALISI VIDEO")
        self.btn_run.setStyleSheet(
            "background-color: #2e7d32; color: white; font-weight: bold; padding: 6px;"
        )
        self.btn_run.setEnabled(False)
        self.btn_run.clicked.connect(self._run_analysis)
        action_bar.addWidget(self.btn_run)

        self.btn_export = QPushButton("ESPORTA CSV")
        self.btn_export.setStyleSheet(
            "background-color: #1565c0; color: white; font-weight: bold; padding: 6px;"
        )
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export_csv)
        action_bar.addWidget(self.btn_export)
        action_bar.addStretch(1)
        root_layout.addLayout(action_bar)

        self.lbl_video_path = QLabel("Nessun video selezionato")
        self.lbl_video_path.setStyleSheet("color: #aaaaaa; font-style: italic;")
        root_layout.addWidget(self.lbl_video_path)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        root_layout.addWidget(self.progress_bar)

        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("font-weight: bold;")
        root_layout.addWidget(self.lbl_count)

        self.preview_label = QLabel("Nessun frame elaborato")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("background-color: #181818; color: #888888; border-radius: 4px;")
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_label.setMinimumHeight(400)
        root_layout.addWidget(self.preview_label, stretch=1)

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

    def _load_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona un video", "", "Video (*.mp4 *.avi *.mov *.mkv)"
        )
        if not path:
            return
        self.video_path = Path(path)
        self.lbl_video_path.setText(f"Video selezionato: {self.video_path.name}")
        self._update_run_button_state()

    def _update_run_button_state(self) -> None:
        self.btn_run.setEnabled(self.video_path is not None and self.model_combo.isEnabled())

    def _run_analysis(self) -> None:
        model_name = self.model_combo.currentText()
        if not model_name or not (MODELS_DIR / model_name).is_file():
            QMessageBox.warning(self, "Seleziona modello", "Selezionare un modello YOLO valido.")
            return
        if self.video_path is None:
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self, "Salva video annotato come", str(self.video_path.with_name(self.video_path.stem + "_annotato.mp4")),
            "Video MP4 (*.mp4)"
        )
        if not save_path:
            return
        self.output_path = Path(save_path)

        model_path = str(MODELS_DIR / model_name)
        self.results.clear()
        self.btn_run.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_count.setText("")

        self.worker = VideoAnalysisWorker(model_path, self.video_path, self.output_path)
        self.worker.progress.connect(self._on_progress)
        self.worker.preview_frame.connect(self._on_preview_frame)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_progress(self, current: int, total: int) -> None:
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def _on_preview_frame(self, frame) -> None:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        target_w = max(self.preview_label.width(), 100)
        target_h = max(self.preview_label.height(), 100)
        pixmap = QPixmap.fromImage(qimg).scaled(
            target_w, target_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(pixmap)

    def _on_finished(self, cumulative_count: int, output_path: str, results: List[PairResult]) -> None:
        self.progress_bar.setVisible(False)
        self.btn_run.setEnabled(True)
        self.results = results
        self.btn_export.setEnabled(bool(self.results))
        self.lbl_count.setText(f"Conteggio cumulativo: {cumulative_count} individui distinti")
        QMessageBox.information(
            self, "Analisi completata",
            f"Video annotato salvato in:\n{output_path}\n\nIndividui distinti rilevati: {cumulative_count}"
        )

    def _on_error(self, message: str) -> None:
        self.progress_bar.setVisible(False)
        self.btn_run.setEnabled(True)
        QMessageBox.critical(self, "Errore di analisi", message)

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Esporta report CSV", "risultati_video.csv", "CSV (*.csv)")
        if path:
            try:
                df = detections_to_dataframe(self.results)
                export_csv(df, path)
            except Exception as exc:
                QMessageBox.critical(self, "Errore esportazione", f"Impossibile esportare il CSV:\n{exc}")
                return
            QMessageBox.information(self, "Esportazione completata", f"File salvato con successo in:\n{path}")
