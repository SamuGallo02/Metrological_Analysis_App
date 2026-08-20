"""
Modulo dell'Interfaccia Grafica Principale (GUI) con Gestione del Training YOLO,
Supporto per la Modifica Manuale dei Rilevamenti tramite SpinBox,
Statistiche per Classe e Prefissi ID Puliti e Compatti (es. Ce-1).

Autore: Samuele Gallo
"""

from __future__ import annotations

import os
import shutil
import socket
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

import cv2
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from core.analysis import ObjectAnalyzer, PairResult, StereoConfig, list_model_classes, render_overlay
from core.calibration import load_calibration, save_calibration
from core.object_classes import ALL_OBJECTS, add_class, load_classes, remove_class
from core.pairing import StereoPairFinder
from core.reporting import compute_summary, detections_to_dataframe, export_csv
from core.tracking import ObjectTracker
from gui.gui_components import HardwareAccelerationWidget

MODELS_DIR = Path("models")
DATASETS_DIR = Path("datasets")
TDATASET_DIR = Path("tDataset")


def check_internet_connection() -> bool:
    """Verifica rapida della presenza di una connessione internet attiva."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except OSError:
        return False


def get_hardware_info() -> Tuple[str, str]:
    """Rileva l'hardware disponibile per l'addestramento YOLO (GPU PyTorch/CUDA, MPS o CPU)."""
    try:
        import torch
        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            return "0", f"GPU CUDA ({device_name} - {vram_gb:.1f} GB VRAM)"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps", "Apple Silicon GPU (MPS)"
    except ImportError:
        pass
    return "cpu", "CPU di sistema (Non ottimizzata per training intensivi)"


def generate_adaptive_prefixes(class_labels: List[str]) -> Dict[str, str]:
    """
    Genera un dizionario {nome_classe: prefisso_univoco_formattato} in modo adattivo.
    Formatta il prefisso in TitleCase (es. 'B', 'Ce').
    """
    cleaned_map = {label: "".join(c for c in label.lower() if c.isalnum()) or "obj" for label in set(class_labels)}
    prefixes: Dict[str, str] = {}

    for original_label, cleaned in cleaned_map.items():
        length = 1
        while True:
            candidate = cleaned[:length]

            conflict = False
            for other_label, other_cleaned in cleaned_map.items():
                if original_label != other_label:
                    if other_cleaned.startswith(candidate):
                        conflict = True
                        break

            if not conflict or length >= len(cleaned):
                prefixes[original_label] = candidate.capitalize()
                break

            length += 1

    final_prefixes: Dict[str, str] = {}
    seen_prefixes: Dict[str, int] = {}

    for label in class_labels:
        base_pref = prefixes.get(label, "Obj")
        if base_pref in seen_prefixes:
            seen_prefixes[base_pref] += 1
            final_prefixes[label] = f"{base_pref}{seen_prefixes[base_pref]}"
        else:
            seen_prefixes[base_pref] = 1
            final_prefixes[label] = base_pref

    return final_prefixes


class ClickableImageLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event) -> None:
        self.clicked.emit()
        super().mousePressEvent(event)


def scan_models(models_dir: Path = MODELS_DIR) -> List[str]:
    if not models_dir.is_dir():
        return []
    return sorted(f.name for f in models_dir.iterdir() if f.suffix.lower() == ".pt")


def scan_datasets(datasets_dir: Path = DATASETS_DIR) -> List[str]:
    if not datasets_dir.is_dir():
        return []
    return sorted(f.name for f in datasets_dir.iterdir() if f.is_dir())


# --- WORKER PER IL TRAINING DI YOLO ---
class TrainingWorker(QThread):
    log_signal = Signal(str)
    finished_signal = Signal(str)
    error_signal = Signal(str)

    def __init__(self, data_yaml: str, base_model: str, epochs: int, imgsz: int, batch: int, device: str) -> None:
        super().__init__()
        self.data_yaml = data_yaml
        self.base_model = base_model
        self.epochs = epochs
        self.imgsz = imgsz
        self.batch = batch
        self.device = device

    def run(self) -> None:
        try:
            from ultralytics import YOLO

            self.log_signal.emit(f"Caricamento modello base: {self.base_model}...")
            model = YOLO(self.base_model)

            self.log_signal.emit(f"Avvio addestramento su device '{self.device}' per {self.epochs} epoche...")
            results = model.train(
                data=self.data_yaml,
                epochs=self.epochs,
                imgsz=self.imgsz,
                batch=self.batch,
                device=self.device,
                project="runs/train",
                name="custom_yolo_model",
                exist_ok=True
            )

            best_model_path = Path(results.save_dir) / "weights" / "best.pt"
            if best_model_path.exists():
                MODELS_DIR.mkdir(exist_ok=True)
                dest_path = MODELS_DIR / f"trained_{self.base_model}"
                shutil.copy2(best_model_path, dest_path)
                self.finished_signal.emit(str(dest_path))
            else:
                self.error_signal.emit("Training terminato ma non è stato trovato il file dei pesi salvato.")

        except Exception as exc:
            self.error_signal.emit(str(exc))


# --- FINESTRA DI GESTIONE TRAINING ---
class TrainingDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gestione Training Nuovo Agente YOLO")
        self.setMinimumSize(680, 580)

        TDATASET_DIR.mkdir(exist_ok=True, parents=True)
        MODELS_DIR.mkdir(exist_ok=True, parents=True)

        self.device_code, self.device_desc = get_hardware_info()
        self.is_online = check_internet_connection()
        self.worker: Optional[TrainingWorker] = None

        self._build_ui()
        self._populate_tdatasets()
        self._check_model_download_status()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        hw_box = QWidget()
        hw_box.setStyleSheet("background-color: #2b2b2b; border-radius: 6px; padding: 10px;")
        hw_layout = QVBoxLayout(hw_box)

        lbl_hw = QLabel(f"<b>Hardware Rilevato:</b> {self.device_desc}")
        hw_layout.addWidget(lbl_hw)

        if self.device_code == "cpu" and self.is_online:
            lbl_colab_info = QLabel("<i>Nota: L'addestramento su CPU può richiedere molto tempo. È consigliata la GPU di Google Colab.</i>")
            lbl_colab_info.setStyleSheet("color: #ffca28;")
            hw_layout.addWidget(lbl_colab_info)

            btn_colab = QPushButton("Apri Google Colab per Training Cloud")
            btn_colab.setStyleSheet("background-color: #f57c00; color: white; font-weight: bold; margin-top: 5px;")
            btn_colab.clicked.connect(self._open_colab)
            hw_layout.addWidget(btn_colab)

        layout.addWidget(hw_box)

        # Pannello diagnostico esteso: permette di verificare lo stato CUDA
        # nel dettaglio e, se necessario, reinstallare PyTorch con supporto
        # GPU direttamente da qui prima di avviare un training pesante.
        self.hw_widget = HardwareAccelerationWidget(self)
        layout.addWidget(self.hw_widget)

        form_layout = QFormLayout()

        tdataset_layout = QHBoxLayout()
        self.combo_tdatasets = QComboBox()
        self.combo_tdatasets.currentIndexChanged.connect(self._on_tdataset_selected)

        btn_add_tdataset = QPushButton("Aggiungi Cartella...")
        btn_add_tdataset.setToolTip("Copia una nuova cartella dataset all'interno di tDataset/")
        btn_add_tdataset.clicked.connect(self._add_tdataset_folder)

        tdataset_layout.addWidget(self.combo_tdatasets, stretch=1)
        tdataset_layout.addWidget(btn_add_tdataset)
        form_layout.addRow("Dataset (training):", tdataset_layout)

        self.lbl_yaml_path = QLabel("Nessun data.yaml trovato")
        self.lbl_yaml_path.setStyleSheet("color: #aaaaaa; font-style: italic;")
        form_layout.addRow("File di Configurazione:", self.lbl_yaml_path)

        model_layout = QHBoxLayout()
        self.combo_base_model = QComboBox()
        self.model_options = [
            "yolo11n-seg.pt", "yolo11s-seg.pt", "yolo11m-seg.pt", "yolo11l-seg.pt",
            "yolov8n-seg.pt", "yolov8s-seg.pt", "yolov8m-seg.pt", "yolov8l-seg.pt",
            "yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolo11l.pt"
        ]
        self.combo_base_model.addItems(self.model_options)
        self.combo_base_model.currentIndexChanged.connect(self._check_model_download_status)

        self.lbl_download_status = QLabel("")
        model_layout.addWidget(self.combo_base_model, stretch=1)
        model_layout.addWidget(self.lbl_download_status)
        form_layout.addRow("Modello Base:", model_layout)

        self.spin_epochs = QSpinBox()
        self.spin_epochs.setRange(1, 1000)
        self.spin_epochs.setValue(50)
        form_layout.addRow("Numero Epoche:", self.spin_epochs)

        self.spin_imgsz = QSpinBox()
        self.spin_imgsz.setRange(320, 2048)
        self.spin_imgsz.setSingleStep(32)
        self.spin_imgsz.setValue(640)
        form_layout.addRow("Dimensione Immagini (px):", self.spin_imgsz)

        self.spin_batch = QSpinBox()
        self.spin_batch.setRange(1, 128)
        self.spin_batch.setValue(8)
        form_layout.addRow("Batch Size:", self.spin_batch)

        layout.addLayout(form_layout)

        layout.addWidget(QLabel("Console di avanzamento:"))
        self.txt_console = QTextEdit()
        self.txt_console.setReadOnly(True)
        self.txt_console.setStyleSheet("background-color: #121212; color: #00ff00; font-family: monospace;")
        layout.addWidget(self.txt_console, stretch=1)

        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("AVVIA TRAINING LOCALE")
        self.btn_start.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 8px;")
        self.btn_start.clicked.connect(self._start_training)

        btn_close = QPushButton("Chiudi")
        btn_close.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _populate_tdatasets(self) -> None:
        self.combo_tdatasets.clear()
        if not TDATASET_DIR.exists():
            return

        subdirs = [d for d in TDATASET_DIR.iterdir() if d.is_dir()]
        if not subdirs:
            self.combo_tdatasets.addItem("Nessun dataset presente", userData=None)
            self.lbl_yaml_path.setText("Manca data.yaml")
            return

        for folder in sorted(subdirs, key=lambda x: x.name):
            yaml_file = folder / "data.yaml"
            if not yaml_file.exists():
                yaml_file = folder / "data.yml"

            if yaml_file.exists():
                self.combo_tdatasets.addItem(f"{folder.name} (✓ data.yaml)", userData=str(yaml_file))
            else:
                self.combo_tdatasets.addItem(f"{folder.name} (✗ Manca data.yaml)", userData=None)

        self._on_tdataset_selected()

    def _on_tdataset_selected(self) -> None:
        yaml_path = self.combo_tdatasets.currentData()
        if yaml_path:
            self.lbl_yaml_path.setText(f"<font color='green'>{yaml_path}</font>")
        else:
            self.lbl_yaml_path.setText("<font color='red'>Nessun file data.yaml trovato in questa cartella</font>")

    def _add_tdataset_folder(self) -> None:
        TDATASET_DIR.mkdir(parents=True, exist_ok=True)
        initial_dir = str(TDATASET_DIR.resolve())

        source_dir = QFileDialog.getExistingDirectory(self, "Seleziona cartella dataset da importare", initial_dir)
        if not source_dir:
            return

        source_path = Path(source_dir)
        if source_path.parent.resolve() == TDATASET_DIR.resolve():
            self._populate_tdatasets()
            for i in range(self.combo_tdatasets.count()):
                if source_path.name in self.combo_tdatasets.itemText(i):
                    self.combo_tdatasets.setCurrentIndex(i)
                    break
            return

        dest_path = TDATASET_DIR / source_path.name
        if dest_path.exists():
            reply = QMessageBox.question(
                self, "Cartella Esistente",
                f"La cartella '{source_path.name}' esiste già in tDataset/. Sovrascrivere?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                shutil.rmtree(dest_path)
            except Exception as e:
                QMessageBox.critical(self, "Errore", f"Impossibile sovrascrivere:\n{e}")
                return

        try:
            shutil.copytree(source_path, dest_path)
            QMessageBox.information(self, "Importazione Completata", f"Dataset '{source_path.name}' importato con successo.")
            self._populate_tdatasets()
            for i in range(self.combo_tdatasets.count()):
                if source_path.name in self.combo_tdatasets.itemText(i):
                    self.combo_tdatasets.setCurrentIndex(i)
                    break
        except Exception as e:
            QMessageBox.critical(self, "Errore di Copia", f"Impossibile importare il dataset:\n{e}")

    def _check_model_download_status(self) -> None:
        model_name = self.combo_base_model.currentText()
        local_path = MODELS_DIR / model_name
        if local_path.is_file():
            self.lbl_download_status.setText("<font color='#4caf50'><b>✓ Scaricato</b></font>")
        else:
            self.lbl_download_status.setText("<font color='#ff9800'><b>↓ Da scaricare</b></font>")

    def _open_colab(self) -> None:
        webbrowser.open("https://colab.research.google.com/#create=true")

    def _start_training(self) -> None:
        yaml_path = self.combo_tdatasets.currentData()
        if not yaml_path or not Path(yaml_path).is_file():
            QMessageBox.warning(self, "Dataset Invalido", "Seleziona un dataset contenente un file data.yaml valido.")
            return

        model_name = self.combo_base_model.currentText()
        model_path = str(MODELS_DIR / model_name) if (MODELS_DIR / model_name).is_file() else model_name

        self.btn_start.setEnabled(False)
        self.txt_console.append(">>> Inizializzazione del processo di training...")

        self.worker = TrainingWorker(
            data_yaml=yaml_path,
            base_model=model_path,
            epochs=self.spin_epochs.value(),
            imgsz=self.spin_imgsz.value(),
            batch=self.spin_batch.value(),
            device=self.device_code
        )
        self.worker.log_signal.connect(self.txt_console.append)
        self.worker.finished_signal.connect(self._on_training_finished)
        self.worker.error_signal.connect(self._on_training_error)
        self.worker.start()

    def _on_training_finished(self, output_path: str) -> None:
        self.btn_start.setEnabled(True)
        self.txt_console.append(f"\n>>> TRAINING COMPLETATO CON SUCCESSO!\n>>> Salvato in: {output_path}")
        self._check_model_download_status()
        QMessageBox.information(self, "Training Completato", f"Modello salvato in:\n{output_path}")

    def _on_training_error(self, err_msg: str) -> None:
        self.btn_start.setEnabled(True)
        self.txt_console.append(f"\n>>> ERRORE DURANTE IL TRAINING:\n{err_msg}")
        QMessageBox.critical(self, "Errore Training", f"Si è verificato un errore:\n{err_msg}")


# --- WORKER DI ANALISI CON FORMATTAZIONE ID ESATTA (es. Ce-1, B-1) ---
class AnalysisWorker(QThread):
    progress = Signal(int, int)
    pair_done = Signal(object, int)
    finished_all = Signal()
    error = Signal(str)

    def __init__(
            self,
            folder: str,
            model_path: str,
            target_label: Optional[Union[str, List[str]]] = None,
            stereo_config: Optional[StereoConfig] = None,
    ) -> None:
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

                        # Estrazione precisa del solo numero finale dell'ID (es. '1' da 'Ce_1' o '1' da '1')
                        str_id = str(det.track_id)
                        num_part = str_id.split("-")[-1].split("_")[-1]

                        # Assegnazione del formato pulito: "Prefix-Numero" (es. Ce-1)
                        det.track_id = f"{prefix}-{num_part}"

                result.overlay_image = render_overlay(result.left_image, result.detections)

                self.pair_done.emit(result, tracker.total_count)
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
        self.setMinimumSize(1300, 850)

        self.results: List[PairResult] = []
        self.user_counts: Dict[int, int] = {}
        self.class_user_counts: Dict[str, int] = {}
        self.worker: Optional[AnalysisWorker] = None
        self.selected_folder: Optional[str] = None
        self.class_checkboxes: Dict[str, QCheckBox] = {}

        self._current_left_image = None
        self._current_right_image = None

        self._load_app_icon()
        self._build_ui()

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

        LABEL_WIDTH = 160

        # 1. BARRA CARTELLA DATASET
        top_bar = QHBoxLayout()
        lbl_dataset = QLabel("Cartella dataset:")
        lbl_dataset.setFixedWidth(LABEL_WIDTH)
        top_bar.addWidget(lbl_dataset)

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

        # 2. BARRA MODELLI YOLO
        model_bar = QHBoxLayout()
        lbl_model = QLabel("Modello YOLO:")
        lbl_model.setFixedWidth(LABEL_WIDTH)
        model_bar.addWidget(lbl_model)

        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(220)
        model_bar.addWidget(self.model_combo, stretch=1)

        btn_add_model = QPushButton("Aggiungi modello...")
        btn_add_model.clicked.connect(self._add_model)
        model_bar.addWidget(btn_add_model)

        btn_refresh_models = QPushButton("Aggiorna elenco")
        btn_refresh_models.clicked.connect(self._refresh_models)
        model_bar.addWidget(btn_refresh_models)

        btn_show_classes = QPushButton("Vedi classi del modello")
        btn_show_classes.clicked.connect(self._show_model_classes)
        model_bar.addWidget(btn_show_classes)
        root_layout.addLayout(model_bar)

        # 3. BARRA CLASSE OGGETTO
        class_bar = QHBoxLayout()
        lbl_class = QLabel("Oggetti da analizzare:")
        lbl_class.setFixedWidth(LABEL_WIDTH)
        class_bar.addWidget(lbl_class)

        self.btn_class_select = QComboBox()
        self.btn_class_select.setMinimumWidth(220)

        self.class_menu = QMenu(self)
        self.btn_class_select.showPopup = lambda: self.class_menu.exec(
            self.btn_class_select.mapToGlobal(self.btn_class_select.rect().bottomLeft())
        )
        class_bar.addWidget(self.btn_class_select, stretch=1)

        btn_add_class = QPushButton("Aggiungi oggetto...")
        btn_add_class.clicked.connect(self._add_object_class)
        class_bar.addWidget(btn_add_class)

        btn_remove_class = QPushButton("Rimuovi oggetto")
        btn_remove_class.clicked.connect(self._remove_object_class)
        class_bar.addWidget(btn_remove_class)
        root_layout.addLayout(class_bar)

        # BARRA PULSANTI AVVIA / ESPORTA / TRAINING
        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(0, 5, 0, 5)

        action_buttons_container = QHBoxLayout()
        action_buttons_container.setSpacing(10)

        self.btn_run = QPushButton("AVVIA ANALISI METROLOGICA")
        self.btn_run.setMinimumHeight(40)
        self.btn_run.setFixedWidth(280)
        self.btn_run.setStyleSheet("""
            QPushButton {
                background-color: #2e7d32; color: white; font-weight: bold; font-size: 13px; border-radius: 5px;
            }
            QPushButton:hover { background-color: #388e3c; }
            QPushButton:disabled { background-color: #444444; color: #888888; }
        """)
        self.btn_run.setEnabled(False)
        self.btn_run.clicked.connect(self._run_analysis)

        self.btn_export = QPushButton("ESPORTA CSV")
        self.btn_export.setMinimumHeight(40)
        self.btn_export.setFixedWidth(160)
        self.btn_export.setStyleSheet("""
            QPushButton {
                background-color: #1565c0; color: white; font-weight: bold; font-size: 13px; border-radius: 5px;
            }
            QPushButton:hover { background-color: #1976d2; }
            QPushButton:disabled { background-color: #444444; color: #888888; }
        """)
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export_csv)

        self.btn_training = QPushButton("TRAINING")
        self.btn_training.setMinimumHeight(40)
        self.btn_training.setFixedWidth(160)
        self.btn_training.setStyleSheet("""
            QPushButton {
                background-color: #d84315; color: white; font-weight: bold; font-size: 13px; border-radius: 5px;
            }
            QPushButton:hover { background-color: #f4511e; }
        """)
        self.btn_training.clicked.connect(self._open_training_dialog)

        action_buttons_container.addWidget(self.btn_run)
        action_buttons_container.addWidget(self.btn_export)
        action_buttons_container.addWidget(self.btn_training)
        action_buttons_container.addStretch(1)

        action_bar.addLayout(action_buttons_container)
        root_layout.addLayout(action_bar)

        # BARRA TOGGLE VISTA
        toggle_bar = QHBoxLayout()
        self.btn_toggle_changes = QPushButton("Mostra solo variazioni")
        self.btn_toggle_changes.setCheckable(True)
        self.btn_toggle_changes.setEnabled(False)
        self.btn_toggle_changes.toggled.connect(self._on_toggle_changes_view)
        toggle_bar.addWidget(self.btn_toggle_changes)
        toggle_bar.addStretch(1)
        root_layout.addLayout(toggle_bar)

        self._refresh_object_classes()
        self._refresh_models()
        self._refresh_datasets()

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        root_layout.addWidget(self.progress_bar)

        # --- PANNELLO CENTRALE ---
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Lista Frame
        self.pair_list = QListWidget()
        self.pair_list.setMinimumWidth(140)
        self.pair_list.setMaximumWidth(500)
        self.pair_list.currentRowChanged.connect(self._show_pair_preview)
        self.splitter.addWidget(self.pair_list)

        # Preview Immagini
        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(5, 5, 5, 5)

        preview_images_layout = QHBoxLayout()
        preview_images_layout.setSpacing(10)

        left_col = QVBoxLayout()
        lbl_left_title = QLabel("Camera Sinistra (lx) + Overlay Rilevamenti")
        lbl_left_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_col.addWidget(lbl_left_title)

        self.preview_left_label = ClickableImageLabel("Nessuna coppia selezionata")
        self.preview_left_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_left_label.setStyleSheet("background-color: #181818; color: #888888; border-radius: 4px;")
        self.preview_left_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_left_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview_left_label.clicked.connect(lambda: self._open_zoom_dialog(self.preview_left_label))
        left_col.addWidget(self.preview_left_label)
        preview_images_layout.addLayout(left_col, stretch=1)

        right_col = QVBoxLayout()
        lbl_right_title = QLabel("Camera Destra (rx)")
        lbl_right_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_col.addWidget(lbl_right_title)

        self.preview_right_label = ClickableImageLabel("Nessuna coppia selezionata")
        self.preview_right_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_right_label.setStyleSheet("background-color: #181818; color: #888888; border-radius: 4px;")
        self.preview_right_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_right_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview_right_label.clicked.connect(lambda: self._open_zoom_dialog(self.preview_right_label))
        right_col.addWidget(self.preview_right_label)
        preview_images_layout.addLayout(right_col, stretch=1)

        preview_layout.addLayout(preview_images_layout)
        self.splitter.addWidget(preview_container)

        # Pannello destro Tabella e Statistiche
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        right_layout.addWidget(QLabel("Calibrazione Fotocamera Stereo"))
        calib_form = QHBoxLayout()

        saved_config = load_calibration()

        calib_form.addWidget(QLabel("Baseline (mm):"))
        self.spin_baseline = QDoubleSpinBox()
        self.spin_baseline.setRange(1.0, 2000.0)
        self.spin_baseline.setDecimals(1)
        self.spin_baseline.setSingleStep(0.5)
        self.spin_baseline.setValue(saved_config.baseline_mm)
        calib_form.addWidget(self.spin_baseline)

        calib_form.addWidget(QLabel("Focale (px):"))
        self.spin_focal = QDoubleSpinBox()
        self.spin_focal.setRange(1.0, 20000.0)
        self.spin_focal.setDecimals(1)
        self.spin_focal.setSingleStep(10.0)
        self.spin_focal.setValue(saved_config.focal_length_px)
        calib_form.addWidget(self.spin_focal)
        calib_form.addStretch(1)

        right_layout.addLayout(calib_form)

        self.spin_baseline.valueChanged.connect(self._save_calibration_fields)
        self.spin_focal.valueChanged.connect(self._save_calibration_fields)

        # NOTA: "Distanza (mm)" nella tabella sotto e' calcolata SOLO tramite
        # triangolazione stereo reale (baseline + focale, gia' impostati sopra),
        # senza bisogno di parametri aggiuntivi di altezza/inclinazione camera.
        # Se la corrispondenza stereo non riesce in un punto, la cella mostra "-".

        right_layout.addWidget(QLabel("Rilevamenti Metrologici"))
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Coppia", "N soggetti", "ID Presenti", "Distanza (mm)",
            "Lunghezza (mm)", "Larghezza (mm)", "Copertura (%)", "Confidenza",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        right_layout.addWidget(self.table)

        # Tabella 1: Statistiche Aggregate per ID
        right_layout.addWidget(QLabel("Statistiche Aggregate per Singolo ID"))
        self.summary_table = QTableWidget(0, 6)
        self.summary_table.setHorizontalHeaderLabels([
            "ID", "Classe", "Apparizioni", "Lunghezza Media (mm)", "Larghezza Media (mm)", "Confidenza Media"
        ])
        self.summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.summary_table.setMaximumHeight(140)
        right_layout.addWidget(self.summary_table)

        # Tabella 2: Statistiche Aggregate per Classe con SpinBox Integrato
        lbl_class_summary = QLabel("Statistiche Aggregate per Classe")
        lbl_class_summary.setStyleSheet("font-weight: bold; margin-top: 5px;")
        right_layout.addWidget(lbl_class_summary)

        self.class_summary_table = QTableWidget(0, 5)
        self.class_summary_table.setHorizontalHeaderLabels([
            "Classe", "N° Soggetti Rilevati", "N° Soggetti Corretto (manuale)", "Lunghezza Media (mm)", "Larghezza Media (mm)"
        ])
        self.class_summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.class_summary_table.setMaximumHeight(150)
        right_layout.addWidget(self.class_summary_table)

        self.splitter.addWidget(right_panel)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setStretchFactor(2, 2)
        self.splitter.setSizes([180, 650, 450])

        root_layout.addWidget(self.splitter, stretch=1)

    def _open_training_dialog(self) -> None:
        dialog = TrainingDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._refresh_models()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, 'pair_list') and self.pair_list.currentRow() >= 0:
            self._show_pair_preview(self.pair_list.currentRow())

    def _current_stereo_config(self) -> StereoConfig:
        return StereoConfig(
            baseline_mm=self.spin_baseline.value(),
            focal_length_px=self.spin_focal.value(),
        )

    def _save_calibration_fields(self, _value: float = 0.0) -> None:
        save_calibration(self._current_stereo_config())

    def _open_zoom_dialog(self, label: QLabel) -> None:
        image = self._current_left_image if label is self.preview_left_label else self._current_right_image
        if image is None:
            return

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)

        screen = self.screen()
        screen_geo = screen.availableGeometry() if screen else None
        max_w = int(screen_geo.width() * 0.9) if screen_geo else 1600
        max_h = int(screen_geo.height() * 0.9) if screen_geo else 1000

        scale_factor = min(1.0, max_w / w, max_h / h)
        target_w = max(1, int(w * scale_factor))
        target_h = max(1, int(h * scale_factor))

        pixmap = QPixmap.fromImage(qimg).scaled(
            target_w, target_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )

        dialog = QDialog(self)
        dialog.setWindowTitle("Anteprima ingrandita")
        dialog_layout = QVBoxLayout(dialog)
        dialog_layout.setContentsMargins(4, 4, 4, 4)

        zoom_label = QLabel()
        zoom_label.setPixmap(pixmap)
        zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dialog_layout.addWidget(zoom_label)

        dialog.resize(pixmap.width() + 16, pixmap.height() + 32)
        dialog.exec()

    def _refresh_object_classes(self) -> None:
        selected_classes = self._get_selected_classes()
        self.class_menu.clear()
        self.class_checkboxes.clear()

        classes = load_classes()

        chk_all = QCheckBox(ALL_OBJECTS)
        chk_all.setStyleSheet("padding: 4px 8px; font-weight: bold;")
        action_all = QWidgetAction(self.class_menu)
        action_all.setDefaultWidget(chk_all)
        self.class_menu.addAction(action_all)
        self.class_checkboxes[ALL_OBJECTS] = chk_all

        if not selected_classes or ALL_OBJECTS in selected_classes:
            chk_all.setChecked(True)

        chk_all.toggled.connect(self._on_all_objects_toggled)

        for cls_name in classes:
            chk = QCheckBox(cls_name)
            chk.setStyleSheet("padding: 4px 8px;")
            if ALL_OBJECTS not in selected_classes and cls_name in selected_classes:
                chk.setChecked(True)

            chk.toggled.connect(self._on_class_checkbox_toggled)

            action = QWidgetAction(self.class_menu)
            action.setDefaultWidget(chk)
            self.class_menu.addAction(action)
            self.class_checkboxes[cls_name] = chk

        self._update_class_button_text()

    def _on_all_objects_toggled(self, checked: bool) -> None:
        if checked:
            for name, chk in self.class_checkboxes.items():
                if name != ALL_OBJECTS:
                    chk.blockSignals(True)
                    chk.setChecked(False)
                    chk.blockSignals(False)
        self._update_class_button_text()

    def _on_class_checkbox_toggled(self, checked: bool) -> None:
        if checked and ALL_OBJECTS in self.class_checkboxes:
            self.class_checkboxes[ALL_OBJECTS].blockSignals(True)
            self.class_checkboxes[ALL_OBJECTS].setChecked(False)
            self.class_checkboxes[ALL_OBJECTS].blockSignals(False)

        if not self._get_selected_classes() and ALL_OBJECTS in self.class_checkboxes:
            self.class_checkboxes[ALL_OBJECTS].blockSignals(True)
            self.class_checkboxes[ALL_OBJECTS].setChecked(True)
            self.class_checkboxes[ALL_OBJECTS].blockSignals(False)

        self._update_class_button_text()

    def _get_selected_classes(self) -> List[str]:
        if not hasattr(self, 'class_checkboxes') or not self.class_checkboxes:
            return [ALL_OBJECTS]

        selected = [name for name, chk in self.class_checkboxes.items() if chk.isChecked()]
        return selected if selected else [ALL_OBJECTS]

    def _update_class_button_text(self) -> None:
        selected = self._get_selected_classes()
        if ALL_OBJECTS in selected or not selected:
            text = "Tutti gli oggetti"
        elif len(selected) == 1:
            text = selected[0]
        else:
            text = f"{len(selected)} classi selezionate ({', '.join(selected)})"

        self.btn_class_select.clear()
        self.btn_class_select.addItem(text)

    def _add_object_class(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Aggiungi oggetto",
            "Nome della classe (deve corrispondere all'etichetta usata dal modello YOLO):"
        )
        if not ok or not name.strip():
            return

        add_class(name.strip())
        self._refresh_object_classes()

    def _remove_object_class(self) -> None:
        selected = [name for name in self._get_selected_classes() if name != ALL_OBJECTS]
        if not selected:
            QMessageBox.information(self, "Nessuna selezione", "Seleziona/spunta almeno una classe specifica da rimuovere.")
            return

        reply = QMessageBox.question(
            self, "Conferma rimozione",
            f"Rimuovere le seguenti classi dall'elenco?\n\n{', '.join(selected)}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for name in selected:
            remove_class(name)

        self._refresh_object_classes()

    def _show_model_classes(self) -> None:
        model_name = self.model_combo.currentText()
        if not model_name or not (MODELS_DIR / model_name).is_file():
            QMessageBox.warning(self, "Nessun modello selezionato", "Seleziona prima un modello valido.")
            return

        try:
            classes = list_model_classes(str(MODELS_DIR / model_name))
        except Exception as exc:
            QMessageBox.critical(self, "Errore caricamento modello", f"Impossibile leggere le classi:\n{exc}")
            return

        if not classes:
            QMessageBox.information(self, "Nessuna classe", "Il modello non espone nomi di classe.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Classi del modello — {model_name}")
        dialog.setMinimumSize(320, 400)
        dialog.resize(350, 450)

        layout = QVBoxLayout(dialog)

        lbl_info = QLabel(f"<b>Etichette rilevabili ({len(classes)} totali):</b>")
        layout.addWidget(lbl_info)

        text_area = QTextEdit()
        text_area.setReadOnly(True)

        listing = "\n".join(f"{i}: {name}" for i, name in enumerate(classes))
        text_area.setPlainText(listing)
        layout.addWidget(text_area)

        btn_close = QPushButton("Chiudi")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)

        dialog.exec()

    def _add_model(self) -> None:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        initial_dir = str(MODELS_DIR.resolve())

        source_path, _ = QFileDialog.getOpenFileName(self, "Seleziona modello YOLO (.pt)", initial_dir, "Modelli YOLO (*.pt)")
        if not source_path:
            return

        source = Path(source_path)
        dest = MODELS_DIR / source.name

        if dest.exists():
            reply = QMessageBox.question(
                self, "File esistente", f"Un modello denominato '{source.name}' è già presente. Sovrascrivere?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            shutil.copy2(source, dest)
        except OSError as exc:
            QMessageBox.critical(self, "Errore di copia", f"Impossibile copiare il file:\n{exc}")
            return

        self._refresh_models()
        self.model_combo.setCurrentText(source.name)

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

    def _add_dataset(self) -> None:
        DATASETS_DIR.mkdir(parents=True, exist_ok=True)
        initial_dir = str(DATASETS_DIR.resolve())

        source_dir = QFileDialog.getExistingDirectory(self, "Seleziona cartella con le acquisizioni stereo", initial_dir)
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
        self._update_run_button_state()

    def _on_folder_selection_changed(self, _index: int) -> None:
        name = self.folder_combo.currentText()
        self.selected_folder = str(DATASETS_DIR / name) if name else None
        self._update_run_button_state()

    def _update_run_button_state(self) -> None:
        self.btn_run.setEnabled(bool(self.selected_folder) and self.model_combo.isEnabled())

    def _run_analysis(self) -> None:
        model_name = self.model_combo.currentText()
        if not model_name or not (MODELS_DIR / model_name).is_file():
            QMessageBox.warning(self, "Seleziona modello", "Selezionare un modello YOLO valido.")
            return

        model_path = str(MODELS_DIR / model_name)
        selected_classes = self._get_selected_classes()

        if ALL_OBJECTS in selected_classes or not selected_classes:
            target_label = None
        elif len(selected_classes) == 1:
            target_label = selected_classes[0]
        else:
            target_label = selected_classes

        self.results.clear()
        self.user_counts.clear()
        self.class_user_counts.clear()
        self.pair_list.clear()
        self.table.setRowCount(0)
        self.summary_table.setRowCount(0)
        self.class_summary_table.setRowCount(0)

        self.btn_toggle_changes.blockSignals(True)
        self.btn_toggle_changes.setChecked(False)
        self.btn_toggle_changes.blockSignals(False)
        self.btn_toggle_changes.setText("Mostra solo variazioni")
        self.btn_toggle_changes.setEnabled(False)

        self.btn_run.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        stereo_config = self._current_stereo_config()
        self.worker = AnalysisWorker(self.selected_folder, model_path, target_label, stereo_config)
        self.worker.progress.connect(self._on_progress)
        self.worker.pair_done.connect(self._on_pair_done)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_progress(self, current: int, total: int) -> None:
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def _on_pair_done(self, result: PairResult, cumulative_count: int) -> None:
        self.results.append(result)
        idx = len(self.results) - 1
        count = self.user_counts.get(idx, cumulative_count)

        item = QListWidgetItem(f"{result.timestamp} ({count} elementi)")
        item.setData(Qt.ItemDataRole.UserRole, (idx, None))
        self.pair_list.addItem(item)

        current_ids = sorted({det.track_id for det in result.detections if det.track_id is not None})
        ids_str = ", ".join(current_ids) if current_ids else "-"

        # Percentuale di pixel del frame coperta dai soggetti rilevati (somma delle
        # aree dei contorni / area totale immagine), calcolata UNA volta per coppia.
        coverage_pct = 0.0
        if result.left_image is not None and result.left_image.size > 0:
            frame_area_px = result.left_image.shape[0] * result.left_image.shape[1]
            covered_px = sum(cv2.contourArea(det.contour) for det in result.detections)
            coverage_pct = (covered_px / frame_area_px) * 100.0 if frame_area_px > 0 else 0.0

        for det in result.detections:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(result.timestamp))
            self.table.setItem(row, 1, QTableWidgetItem(str(count)))
            self.table.setItem(row, 2, QTableWidgetItem(ids_str))
            self.table.setItem(
                row, 3,
                QTableWidgetItem(f"{det.contact_distance_mm:.1f}" if det.contact_distance_mm is not None else "-")
            )
            self.table.setItem(
                row, 4, QTableWidgetItem(f"{det.length_mm:.1f}" if det.length_mm is not None else "-")
            )
            self.table.setItem(
                row, 5, QTableWidgetItem(f"{det.width_mm:.1f}" if det.width_mm is not None else "-")
            )
            self.table.setItem(row, 6, QTableWidgetItem(f"{coverage_pct:.2f}"))
            self.table.setItem(row, 7, QTableWidgetItem(f"{det.confidence:.2f}"))

    def _on_finished(self) -> None:
        self.progress_bar.setVisible(False)
        self.btn_run.setEnabled(True)
        self.btn_export.setEnabled(bool(self.results))
        self.btn_toggle_changes.setEnabled(bool(self.results))
        self._update_summary()

        if self.pair_list.count() > 0:
            self.pair_list.setCurrentRow(0)

    def _on_error(self, message: str) -> None:
        self.progress_bar.setVisible(False)
        self.btn_run.setEnabled(True)
        QMessageBox.critical(self, "Errore di analisi", message)

    def _compute_changes_info(self) -> List[dict]:
        changes_info = []
        prev_ids: Set[str] = set()

        for idx, result in enumerate(self.results):
            current_ids = {det.track_id for det in result.detections if det.track_id is not None}

            if idx == 0:
                if current_ids:
                    changes_info.append({"index": idx, "target_ids": current_ids})
            else:
                added = current_ids - prev_ids
                removed = prev_ids - current_ids
                changed_ids = added | removed

                if changed_ids:
                    changes_info.append({"index": idx, "target_ids": changed_ids})

            prev_ids = current_ids

        return changes_info

    def _build_change_blocks(self) -> List[dict]:
        changes = self._compute_changes_info()
        total = len(self.results)
        blocks = []

        for change in changes:
            c_idx = change["index"]
            start_idx = max(0, c_idx - 2)
            end_idx = min(total - 1, c_idx + 2)

            blocks.append({
                "var_index": c_idx,
                "target_ids": change["target_ids"],
                "range": list(range(start_idx, end_idx + 1))
            })

        return blocks

    def _rebuild_pair_list_full(self) -> None:
        self.pair_list.clear()
        for idx, result in enumerate(self.results):
            count = self.user_counts.get(idx, len(result.detections))
            item = QListWidgetItem(f"{result.timestamp} ({count} elementi)")
            item.setData(Qt.ItemDataRole.UserRole, (idx, None))
            self.pair_list.addItem(item)

    def _rebuild_pair_list_filtered(self) -> None:
        self.pair_list.clear()
        blocks = self._build_change_blocks()

        if not blocks:
            placeholder = QListWidgetItem("Nessuna variazione rilevata nella sequenza.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.pair_list.addItem(placeholder)
            return

        for block_num, block in enumerate(blocks, start=1):
            var_idx = block["var_index"]
            target_ids = block["target_ids"]

            header = QListWidgetItem(f"── Blocco {block_num} ──")
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            self.pair_list.addItem(header)

            for idx in block["range"]:
                result = self.results[idx]
                count = self.user_counts.get(idx, len(result.detections))

                if idx == var_idx:
                    item_text = f"Variazione {block_num} - {result.timestamp} ({count} elementi)"
                else:
                    item_text = f"{result.timestamp} ({count} elementi)"

                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, (idx, target_ids))
                self.pair_list.addItem(item)

    def _on_toggle_changes_view(self, checked: bool) -> None:
        if checked:
            self._rebuild_pair_list_filtered()
            self.btn_toggle_changes.setText("Mostra tutte le coppie")
        else:
            self._rebuild_pair_list_full()
            self.btn_toggle_changes.setText("Mostra solo variazioni")

        for i in range(self.pair_list.count()):
            item = self.pair_list.item(i)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) is not None:
                self.pair_list.setCurrentRow(i)
                break

    def _update_summary(self) -> None:
        try:
            df = detections_to_dataframe(self.results)
            summary_df = compute_summary(df)

            self.summary_table.setRowCount(0)
            if not summary_df.empty:
                for _, row in summary_df.iterrows():
                    r = self.summary_table.rowCount()
                    self.summary_table.insertRow(r)
                    self.summary_table.setItem(r, 0, QTableWidgetItem(str(row["ID"])))
                    self.summary_table.setItem(r, 1, QTableWidgetItem(str(row["Classe"])))
                    self.summary_table.setItem(r, 2, QTableWidgetItem(str(row["Apparizioni"])))
                    self.summary_table.setItem(r, 3, QTableWidgetItem(f"{row['Lunghezza Media (mm)']:.2f}"))
                    self.summary_table.setItem(r, 4, QTableWidgetItem(f"{row['Larghezza Media (mm)']:.2f}"))
                    self.summary_table.setItem(r, 5, QTableWidgetItem(f"{row['Confidenza Media']:.3f}"))

            # Popolamento Tabella Statistiche Aggregate per Classe con QSpinBox
            self.class_summary_table.setRowCount(0)

            if not df.empty:
                grouped = df.groupby("label")
                for cls_name, group in grouped:
                    r = self.class_summary_table.rowCount()
                    self.class_summary_table.insertRow(r)

                    detected_count = len(group["track_id"].unique())
                    corrected_count = self.class_user_counts.get(cls_name, detected_count)

                    # Colonna 0: Classe
                    item_cls = QTableWidgetItem(str(cls_name))
                    item_cls.setFlags(item_cls.flags() & ~Qt.ItemFlag.ItemIsEditable)

                    # Colonna 1: N° Soggetti Rilevati
                    item_det = QTableWidgetItem(str(detected_count))
                    item_det.setFlags(item_det.flags() & ~Qt.ItemFlag.ItemIsEditable)

                    # Colonna 2: SpinBox integrato con stile di sistema neutro
                    spin = QSpinBox()
                    spin.setRange(0, 99999)
                    spin.setValue(corrected_count)

                    # Connessione al segnale di cambio valore
                    spin.valueChanged.connect(
                        lambda val, name=cls_name: self._on_class_spinbox_changed(name, val)
                    )

                    # Colonna 3 & 4: Medie
                    avg_len = group["length_mm"].mean()
                    item_len = QTableWidgetItem(f"{avg_len:.2f}")
                    item_len.setFlags(item_len.flags() & ~Qt.ItemFlag.ItemIsEditable)

                    avg_wid = group["width_mm"].mean()
                    item_wid = QTableWidgetItem(f"{avg_wid:.2f}")
                    item_wid.setFlags(item_wid.flags() & ~Qt.ItemFlag.ItemIsEditable)

                    self.class_summary_table.setItem(r, 0, item_cls)
                    self.class_summary_table.setItem(r, 1, item_det)
                    self.class_summary_table.setCellWidget(r, 2, spin)
                    self.class_summary_table.setItem(r, 3, item_len)
                    self.class_summary_table.setItem(r, 4, item_wid)

        except Exception as exc:
            QMessageBox.critical(self, "Errore", f"Impossibile aggiornare la tabella riassuntiva:\n{exc}")

    def _on_class_spinbox_changed(self, class_name: str, new_value: int) -> None:
        """Aggiorna il conteggio memorizzato quando si usano i pulsanti dello SpinBox."""
        self.class_user_counts[class_name] = new_value

    def _show_pair_preview(self, row: int) -> None:
        if row < 0 or row >= self.pair_list.count():
            return

        item = self.pair_list.item(row)
        if item is None:
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        if data is None:
            return

        idx, target_ids = data
        if idx < 0 or idx >= len(self.results):
            return

        result = self.results[idx]
        filtered_overlay = render_overlay(result.left_image, result.detections, filter_ids=target_ids)

        self._current_left_image = filtered_overlay
        self._current_right_image = result.right_image
        self._render_preview(self.preview_left_label, filtered_overlay)
        self._render_preview(self.preview_right_label, result.right_image)

    @staticmethod
    def _render_preview(label: QLabel, image) -> None:
        if image is None:
            label.setText("Immagine non disponibile")
            label.setPixmap(QPixmap())
            return

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)

        target_w = max(label.width(), 100)
        target_h = max(label.height(), 100)

        pixmap = QPixmap.fromImage(qimg).scaled(
            target_w, target_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        label.setPixmap(pixmap)

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Esporta report CSV", "risultati_metrologia.csv", "CSV (*.csv)")
        if path:
            try:
                df = detections_to_dataframe(self.results)
                export_csv(df, path)
            except Exception as exc:
                QMessageBox.critical(self, "Errore esportazione", f"Impossibile esportare il CSV:\n{exc}")
                return
            QMessageBox.information(self, "Esportazione completata", f"File salvato con successo in:\n{path}")