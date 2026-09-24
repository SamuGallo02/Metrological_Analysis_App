"""
Modulo della Home Page e della Finestra Applicativa Principale.
Instrada l'utente verso una delle quattro sezioni (Analisi Stereo, Training,
Analisi Foto Singola, Analisi Video), tutte ospitate nella stessa finestra
tramite QStackedWidget.

Autore: Samuele Gallo
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui.analysis_gui import StereoAnalysisPage
from gui.single_photo_gui import SinglePhotoPage
from gui.training_gui import TrainingPage
from gui.video_gui import VideoPage

# Indici delle pagine nello stack
IDX_HOME = 0
IDX_STEREO = 1
IDX_TRAINING = 2
IDX_SINGLE_PHOTO = 3
IDX_VIDEO = 4


class HomePage(QWidget):
    """Schermata iniziale con i quattro percorsi disponibili."""

    def __init__(self, on_navigate, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.on_navigate = on_navigate
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addStretch(1)

        title = QLabel("Stereo Metrology Analysis")
        title.setStyleSheet("font-size: 26px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Seleziona la modalità di analisi")
        subtitle.setStyleSheet("font-size: 14px; color: #888888;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(30)

        grid = QGridLayout()
        grid.setSpacing(20)

        buttons = [
            ("Analisi Stereo", "Analisi metrologica completa su coppie di immagini stereo (rx/lx):\ndimensioni e distanze reali.", IDX_STEREO, "#2e7d32"),
            ("Training", "Addestra un nuovo modello YOLO su un dataset annotato.", IDX_TRAINING, "#d84315"),
            ("Analisi Foto Singola", "Rilevamento e segmentazione su una singola immagine:\nclasse e confidenza, nessuna misura.", IDX_SINGLE_PHOTO, "#1565c0"),
            ("Analisi Video", "Rilevamento e tracciamento su un video:\nconteggio cumulativo, video annotato in output.", IDX_VIDEO, "#6a1b9a"),
        ]

        for i, (label, description, target_idx, color) in enumerate(buttons):
            btn = QPushButton(f"{label}\n\n{description}")
            btn.setMinimumSize(320, 140)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color}; color: white; font-weight: bold;
                    font-size: 14px; border-radius: 8px; padding: 10px; text-align: center;
                }}
                QPushButton:hover {{ background-color: {color}; opacity: 0.9; }}
            """)
            btn.clicked.connect(lambda _checked=False, idx=target_idx: self.on_navigate(idx))
            grid.addWidget(btn, i // 2, i % 2)

        grid_container = QWidget()
        grid_container.setLayout(grid)
        centered_layout = QVBoxLayout()
        centered_layout.addWidget(grid_container)
        layout.addLayout(centered_layout)

        layout.addStretch(2)


class AppWindow(QMainWindow):
    """Finestra principale dell'applicazione: ospita la home e tutte le sezioni in uno QStackedWidget."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Stereo Metrology Analysis — YOLO")
        self.setMinimumSize(1300, 850)

        self._load_app_icon()

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.home_page = HomePage(on_navigate=self._navigate)
        self.stereo_page = StereoAnalysisPage(
            on_home=self._go_home,
            navigate_to_training=lambda: self._navigate(IDX_TRAINING),
        )
        self.training_page = TrainingPage(on_home=self._go_home)
        self.single_photo_page = SinglePhotoPage(on_home=self._go_home)
        self.video_page = VideoPage(on_home=self._go_home)

        # L'ordine di inserimento DEVE corrispondere agli indici IDX_* sopra.
        self.stack.addWidget(self.home_page)         # IDX_HOME = 0
        self.stack.addWidget(self.stereo_page)        # IDX_STEREO = 1
        self.stack.addWidget(self.training_page)      # IDX_TRAINING = 2
        self.stack.addWidget(self.single_photo_page)  # IDX_SINGLE_PHOTO = 3
        self.stack.addWidget(self.video_page)          # IDX_VIDEO = 4

        self.stack.setCurrentIndex(IDX_HOME)

    def _load_app_icon(self) -> None:
        base_dir = Path(__file__).parent.parent / "assets"
        icon_path = base_dir / "app_icon.ico"
        if not icon_path.exists():
            icon_path = base_dir / "app_icon.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _navigate(self, index: int) -> None:
        self.stack.setCurrentIndex(index)

    def _go_home(self) -> None:
        self.stack.setCurrentIndex(IDX_HOME)
