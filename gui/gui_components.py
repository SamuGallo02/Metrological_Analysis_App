"""
Componente dell'interfaccia utente (PySide6) per l'accelerazione hardware.
Nella pagina di training permette di installare, su richiesta, i componenti
necessari all'addestramento (PyTorch con supporto GPU): non vengono mai
installati in automatico.

Autore: Samuele Gallo
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

from core.environment_manager import get_cuda_status, launch_training_installer


class HardwareAccelerationWidget(QGroupBox):
    """Stato dell'accelerazione GPU e installazione opzionale dei componenti di training."""

    def __init__(self, parent=None):
        super().__init__("Componenti di training e accelerazione hardware", parent)
        self._status = {}
        self.init_ui()
        self.refresh_hardware_status()

    def init_ui(self):
        layout = QVBoxLayout()

        self.status_label = QLabel()
        self.device_label = QLabel()
        self.torch_label = QLabel()
        for lbl in (self.status_label, self.device_label, self.torch_label):
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setWordWrap(True)

        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("Diagnostica Hardware")
        self.btn_refresh.clicked.connect(self.refresh_hardware_status)

        self.btn_install = QPushButton()
        self.btn_install.clicked.connect(self.start_training_installation)

        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_install)

        layout.addWidget(self.status_label)
        layout.addWidget(self.device_label)
        layout.addWidget(self.torch_label)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def refresh_hardware_status(self):
        s = get_cuda_status()
        self._status = s

        if s["cuda_available"]:
            self.status_label.setText("<b>Accelerazione Hardware:</b> <font color='green'>ATTIVA (GPU CUDA)</font>")
            self.device_label.setText(f"<b>GPU Dedicata:</b> {s['device_name']}")
        elif s["apple_silicon"]:
            self.status_label.setText("<b>Accelerazione Hardware:</b> <font color='green'>Apple GPU (MPS)</font>")
            self.device_label.setText(f"<b>Nota:</b> {s['install_note']}")
        else:
            self.status_label.setText("<b>Accelerazione Hardware:</b> <font color='orange'>Modalità CPU</font>")
            if s["install_needed"]:
                self.device_label.setText(
                    f"<b>GPU rilevata:</b> {s['gpu_name'] or 'NVIDIA'}. PyTorch e' in versione CPU: attiva "
                    f"l'accelerazione GPU (build {s['install_variant']}, download di alcuni GB).")
            else:
                self.device_label.setText(f"<b>Nota:</b> {s['install_note']}")

        self.torch_label.setText(f"<b>Versione PyTorch:</b> {s['torch_version']}")
        if s["install_needed"]:
            self.btn_install.setText("Attiva accelerazione GPU (CUDA)")
        elif s["extras_pending"]:
            self.btn_install.setText("Installa extra per il training")
        self.btn_install.setVisible(s["install_needed"] or s["extras_pending"])

    def start_training_installation(self, confirm=True):
        s = self._status
        what = (f"PyTorch con supporto GPU ({s['install_variant']}, alcuni GB)" if s["install_needed"]
                else "gli extra per il training (pochi MB)")
        reply = QMessageBox.StandardButton.Yes if not confirm else QMessageBox.question(
            self,
            "Installa componenti",
            f"Verranno scaricati {what}.\n\n"
            "L'applicativo si chiuderà durante l'installazione e si riaprirà da solo al termine "
            "(possono servire diversi minuti; su Windows compare una finestra con l'avanzamento).\n\n"
            "Continuare?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if launch_training_installer():
            QApplication.quit()
        else:
            QMessageBox.critical(self, "Errore", "Impossibile avviare l'installazione. "
                                 "Riesegui l'installer del tuo sistema operativo.")
