"""
User interface component (PySide6) for hardware acceleration.
In the training page it lets you install, on request, the components
needed for training (PyTorch with GPU support): they are never
installed automatically.

Autore: Samuele Gallo
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from corpse.functions.training.environment_manager import get_cuda_status


class HardwareAccelerationWidget(QGroupBox):
    """GPU acceleration status and optional installation of the training components."""

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

    def start_training_installation(self, *_):
        """Same flow as the Train button: confirmation, progress window, no console."""
        from .setup_dialog import ensure_training_ready
        ensure_training_ready(self)
