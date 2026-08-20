"""
Componente dell'interfaccia utente (PySide6) per il monitoraggio delle risorse di calcolo.
Permette la gestione dell'hardware per il riconoscimento di specie marine.
"""

from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QMessageBox, QProgressBar
)
from PySide6.QtCore import Qt, QThread, Signal
from environment_manager import get_cuda_status, install_pytorch_environment


class InstallationWorker(QThread):
    """Thread secondario per l'aggiornamento dei moduli di calcolo in background."""
    finished_signal = Signal(bool)

    def run(self):
        result = install_pytorch_environment(force_cuda=True)
        self.finished_signal.emit(result)


class MarineHardwareWidget(QGroupBox):
    """Widget di controllo dell'accelerazione GPU per il modello di fauna marina."""
    
    def __init__(self, parent=None):
        super().__init__("Pannello Accelerazione Hardware (Riconoscimento Fauna Marina)", parent)
        self.worker = None
        self.init_ui()
        self.refresh_hardware_status()

    def init_ui(self):
        layout = QVBoxLayout()

        # Informazioni diagnostiche
        self.status_label = QLabel("Stato Elaborazione: Analisi hardware in corso...")
        self.device_label = QLabel("Unità di Calcolo: -")
        self.torch_label = QLabel("Framework Deep Learning: -")

        self.status_label.setTextFormat(Qt.TextFormat.RichText)
        self.device_label.setTextFormat(Qt.TextFormat.RichText)
        self.torch_label.setTextFormat(Qt.TextFormat.RichText)

        # Pulsanti di comando
        btn_layout = QHBoxLayout()

        self.btn_refresh = QPushButton("Diagnostica Hardware")
        self.btn_refresh.clicked.connect(self.refresh_hardware_status)

        self.btn_reinstall = QPushButton("Attiva Accelerazione GPU (CUDA)")
        self.btn_reinstall.setToolTip("Configura PyTorch con supporto CUDA per accelerare il rilevamento della fauna marina.")
        self.btn_reinstall.clicked.connect(self.start_cuda_configuration)

        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_reinstall)

        # Barra di caricamento
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)

        layout.addWidget(self.status_label)
        layout.addWidget(self.device_label)
        layout.addWidget(self.torch_label)
        layout.addLayout(btn_layout)
        layout.addWidget(self.progress_bar)

        self.setLayout(layout)

    def refresh_hardware_status(self):
        """Aggiorna lo stato visivo relativo alla GPU."""
        status = get_cuda_status()

        if status.get("cuda_available", False):
            self.status_label.setText("<b>Accelerazione Hardware:</b> <font color='green'>ATTIVA (GPU CUDA)</font>")
            self.device_label.setText(f"<b>GPU Dedicata:</b> {status.get('device_name', 'N/D')}")
        else:
            self.status_label.setText("<b>Accelerazione Hardware:</b> <font color='orange'>INATTIVA (Modalità CPU)</font>")
            if status.get("has_nvidia_driver", False):
                self.device_label.setText("<b>Nota:</b> GPU NVIDIA presente. Attivare i binding CUDA per ottimizzare le prestazioni.")
            else:
                self.device_label.setText("<b>Nota:</b> Nessun acceleratore compatibile rilevato.")

        self.torch_label.setText(f"<b>Versione PyTorch:</b> {status.get('torch_version', 'N/D')}")

    def start_cuda_configuration(self):
        """Avvia l'installazione guidata."""
        reply = QMessageBox.question(
            self,
            "Configurazione Acceleratore GPU",
            "Si sta per avviare il download e l'installazione dei moduli PyTorch CUDA 12.1.\n"
            "Questa operazione ottimizza la velocità di inferenza sui video marini. Continuare?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.btn_reinstall.setEnabled(False)
            self.btn_refresh.setEnabled(False)
            self.progress_bar.setVisible(True)

            # Gestione sicura del thread
            self.worker = InstallationWorker()
            self.worker.finished_signal.connect(self.on_installation_finished)
            self.worker.finished.connect(self.worker.deleteLater)
            self.worker.start()

    def on_installation_finished(self, success: bool):
        """Notifica l'esito al termine dell'operazione."""
        self.progress_bar.setVisible(False)
        self.btn_reinstall.setEnabled(True)
        self.btn_refresh.setEnabled(True)

        if success:
            QMessageBox.information(
                self,
                "Operazione Completata",
                "Configurazione completata con successo.\n\n"
                "Nota: Per rendere effettivi i nuovi binding CUDA in PyTorch, riavvia l'applicazione."
            )
        else:
            QMessageBox.critical(
                self, 
                "Errore di Configurazione", 
                "Impossibile completare l'installazione delle librerie CUDA.\nVerificare la connessione ad Internet o i log di sistema."
            )
        
        self.refresh_hardware_status()