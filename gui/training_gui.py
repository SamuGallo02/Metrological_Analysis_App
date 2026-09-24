"""
Modulo dell'Interfaccia Grafica per il Training di un Nuovo Modello YOLO.

Autore: Samuele Gallo
"""

from __future__ import annotations

import shutil
import webbrowser
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.gui_components import HardwareAccelerationWidget

MODELS_DIR = Path("models")
TDATASET_DIR = Path("tDataset")


def check_internet_connection() -> bool:
    """Verifica rapida della presenza di una connessione internet attiva."""
    import socket
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except OSError:
        return False


def get_hardware_info() -> tuple[str, str]:
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


class TrainingWorker(QThread):
    """Thread secondario che esegue l'addestramento YOLO senza bloccare la GUI."""
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


class TrainingPage(QWidget):
    """
    Pagina di gestione del training di un nuovo agente YOLO.
    Prima era una finestra modale (TrainingDialog); ora e' una delle sezioni
    raggiungibili dalla home, con un pulsante per tornare indietro.
    """

    def __init__(self, on_home, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.on_home = on_home
        self.worker: Optional[TrainingWorker] = None

        TDATASET_DIR.mkdir(exist_ok=True, parents=True)
        MODELS_DIR.mkdir(exist_ok=True, parents=True)

        self.device_code, self.device_desc = get_hardware_info()
        self.is_online = check_internet_connection()

        self._build_ui()
        self._populate_tdatasets()
        self._check_model_download_status()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        btn_back = QPushButton("← Torna alla home")
        btn_back.clicked.connect(self.on_home)
        top_bar.addWidget(btn_back)
        top_bar.addStretch(1)
        layout.addLayout(top_bar)

        title = QLabel("<h2>Addestramento Nuovo Modello YOLO</h2>")
        layout.addWidget(title)

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

        # Pannello diagnostico esteso: permette di verificare lo stato CUDA nel
        # dettaglio e, se necessario, reinstallare PyTorch con supporto GPU
        # direttamente da qui prima di avviare un training pesante.
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

        self.btn_start = QPushButton("AVVIA TRAINING LOCALE")
        self.btn_start.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 8px;")
        self.btn_start.clicked.connect(self._start_training)
        layout.addWidget(self.btn_start)

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
