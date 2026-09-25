"""
Modulo della Home Page e della Finestra Applicativa Principale.
Instrada l'utente verso una delle sezioni disponibili, tutte ospitate nella
stessa finestra tramite QStackedWidget. Ordine dei quattro percorsi (come
richiesto): Analisi Stereo, Analisi Foto, Analisi Video, Training (in fondo).
Foto e Video passano prima da una schermata di scelta Singola/Stereo — per
lo Stereo (sia foto che video-stereo, quest'ultimo con misure reali) si
riusano le stesse pagine raggiungibili anche direttamente dalla home.

Autore: Samuele Gallo
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from core.analysis import list_model_classes
from gui.analysis_gui import StereoAnalysisPage
from gui.analysis_page_base import MODELS_DIR, scan_models
from gui.common_widgets import ManualDialog
from gui.home_layout import centered_content
from gui.mode_selector_gui import FotoModeSelectorPage, VideoModeSelectorPage
from gui.photo_gui import PhotoAnalysisPage
from gui.training_gui import TrainingPage
from gui.video_gui import VideoAnalysisPage
from gui.video_stereo_gui import VideoStereoAnalysisPage

# Indici delle pagine nello stack
IDX_HOME = 0
IDX_STEREO = 1              # raggiungibile direttamente, e riusata da "Foto -> Stereo" e "Video -> Stereo"
IDX_FOTO_SELECTOR = 2
IDX_FOTO_SINGOLA = 3
IDX_VIDEO_SELECTOR = 4
IDX_VIDEO_SINGOLO = 5
IDX_VIDEO_STEREO = 6
IDX_TRAINING = 7


class WebcamDemoDialog(QDialog):
    """
    Dialogo mostrato prima di avviare la demo webcam: sceglie quale modello
    YOLO usare e cosa riconoscere. L'elenco delle classi viene letto DAL
    MODELLO SCELTO (list_model_classes), non da un elenco fisso — cosi'
    corrisponde sempre davvero a cio' che quel modello sa riconoscere.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Demo Webcam — configurazione")
        self.resize(380, 160)
        self.selected_model_path: str | None = None
        self.selected_class: str | None = None  # None = tutti gli oggetti

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Modello YOLO:"))
        self.combo_model = QComboBox()
        self.combo_model.currentIndexChanged.connect(self._refresh_classes)
        layout.addWidget(self.combo_model)

        layout.addWidget(QLabel("Cosa riconoscere:"))
        self.combo_class = QComboBox()
        layout.addWidget(self.combo_class)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_cancel = QPushButton("Annulla")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_start = QPushButton("Avvia")
        btn_start.setStyleSheet(
            "background-color: #2e7d32; color: white; font-weight: bold; padding: 5px 14px;"
        )
        btn_start.clicked.connect(self._on_start)
        btn_row.addWidget(btn_start)
        layout.addLayout(btn_row)

        self._populate_models()

    def _populate_models(self) -> None:
        models = scan_models()
        self.combo_model.clear()
        if not models:
            self.combo_model.addItem("Nessun modello trovato in models/")
            self.combo_model.setEnabled(False)
        else:
            self.combo_model.setEnabled(True)
            self.combo_model.addItems(models)
        self._refresh_classes()

    def _refresh_classes(self) -> None:
        self.combo_class.clear()
        self.combo_class.addItem("Tutti gli oggetti")

        model_name = self.combo_model.currentText()
        model_path = MODELS_DIR / model_name
        if model_path.is_file():
            try:
                classes = list_model_classes(str(model_path))
                self.combo_class.addItems(classes)
            except Exception:
                pass  # se la lettura fallisce, resta comunque disponibile "Tutti gli oggetti"

        # preseleziona "person" quando presente, per coerenza col comportamento di default finora
        idx = self.combo_class.findText("person")
        if idx >= 0:
            self.combo_class.setCurrentIndex(idx)

    def _on_start(self) -> None:
        model_name = self.combo_model.currentText()
        model_path = MODELS_DIR / model_name
        if not model_path.is_file():
            QMessageBox.warning(self, "Nessun modello", "Seleziona un modello YOLO valido.")
            return

        self.selected_model_path = str(model_path)
        chosen_class = self.combo_class.currentText()
        self.selected_class = None if chosen_class == "Tutti gli oggetti" else chosen_class
        self.accept()


class MenuCard(QFrame):
    """Scheda personalizzata per ciascuna modalita' con titolo e descrizione ad andata a capo automatica."""

    def __init__(self, title: str, description: str, color: str, onClick=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.onClick = onClick
        self.setMinimumSize(280, 160)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {color};
                border-radius: 10px;
            }}
            QFrame:hover {{
                background-color: {color}dd;
            }}
        """)

        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(15, 15, 15, 15)
        card_layout.setSpacing(8)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_title = QLabel(title)
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: white; background: transparent;")

        lbl_desc = QLabel(description)
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("font-size: 12px; color: #f0f0f0; background: transparent;")

        card_layout.addWidget(lbl_title)
        card_layout.addWidget(lbl_desc)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.onClick:
            self.onClick()
        super().mousePressEvent(event)


class HomePage(QWidget):
    """Schermata iniziale con i quattro percorsi disponibili, in ordine: Stereo, Foto, Video, Training."""

    def __init__(self, on_navigate, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.on_navigate = on_navigate
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        top_bar = QHBoxLayout()

        btn_webcam_demo = QPushButton("🎥 Demo Webcam")
        btn_webcam_demo.setToolTip("Avvia in una finestra separata il rilevamento YOLO dal vivo dalla webcam.")
        btn_webcam_demo.clicked.connect(self._launch_webcam_demo)
        top_bar.addWidget(btn_webcam_demo)

        top_bar.addStretch(1)
        btn_manual = QPushButton("Manuale d'uso (WIP)")
        btn_manual.clicked.connect(lambda: ManualDialog(self).exec())
        top_bar.addWidget(btn_manual)
        layout.addLayout(top_bar)

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
            ("Analisi Foto", "Rilevamento e segmentazione su una o più foto: singola o stereo, a scelta.", IDX_FOTO_SELECTOR, "#1565c0"),
            ("Analisi Video", "Rilevamento e tracciamento su un video: singolo o stereo, a scelta.", IDX_VIDEO_SELECTOR, "#6a1b9a"),
            ("Training", "Addestra un nuovo modello YOLO su un dataset annotato.", IDX_TRAINING, "#d84315"),
        ]

        for i, (label, description, target_idx, color) in enumerate(buttons):
            card = MenuCard(
                title=label,
                description=description,
                color=color,
                onClick=lambda idx=target_idx: self.on_navigate(idx)
            )
            grid.addWidget(card, 0, i)

        layout.addLayout(centered_content(grid, max_width=960))
        layout.addStretch(2)

    def _launch_webcam_demo(self) -> None:
        """
        Avvia tools/webcam_demo.py come processo indipendente (non bloccante):
        l'app principale resta utilizzabile mentre la finestra della demo e'
        aperta. Prima chiede, tramite WebcamDemoDialog, quale modello usare e
        cosa riconoscere — invece di affidarsi sempre ai valori di default.
        """
        import subprocess
        import sys

        project_root = Path(__file__).resolve().parent.parent
        script_path = project_root / "tools" / "webcam_demo.py"

        if not script_path.is_file():
            QMessageBox.critical(
                self, "Demo non trovata",
                f"File non trovato:\n{script_path}"
            )
            return

        if not MODELS_DIR.is_dir() or not any(MODELS_DIR.glob("*.pt")):
            QMessageBox.warning(
                self, "Nessun modello disponibile",
                "Metti almeno un modello YOLO (.pt) nella cartella models/ prima di avviare la demo."
            )
            return

        dialog = WebcamDemoDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        args = [sys.executable, str(script_path), "--model", dialog.selected_model_path]
        args += ["--class", dialog.selected_class if dialog.selected_class is not None else "all"]

        try:
            subprocess.Popen(args, cwd=str(project_root))
        except Exception as exc:
            QMessageBox.critical(self, "Errore all'avvio della demo", f"Impossibile avviare la demo:\n{exc}")


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
        self.stereo_page = StereoAnalysisPage(on_home=self._go_home)
        self.foto_selector_page = FotoModeSelectorPage(
            on_home=self._go_home,
            on_singola=lambda: self._navigate(IDX_FOTO_SINGOLA),
            on_stereo=lambda: self._navigate(IDX_STEREO),
        )
        self.foto_singola_page = PhotoAnalysisPage(on_home=self._go_home)
        self.video_selector_page = VideoModeSelectorPage(
            on_home=self._go_home,
            on_singolo=lambda: self._navigate(IDX_VIDEO_SINGOLO),
            on_stereo=lambda: self._navigate(IDX_VIDEO_STEREO),
        )
        self.video_singolo_page = VideoAnalysisPage(on_home=self._go_home)
        self.video_stereo_page = VideoStereoAnalysisPage(on_home=self._go_home)
        self.training_page = TrainingPage(on_home=self._go_home)

        # L'ordine di inserimento DEVE corrispondere agli indici IDX_* sopra.
        self.stack.addWidget(self.home_page)             # IDX_HOME = 0
        self.stack.addWidget(self.stereo_page)            # IDX_STEREO = 1
        self.stack.addWidget(self.foto_selector_page)     # IDX_FOTO_SELECTOR = 2
        self.stack.addWidget(self.foto_singola_page)      # IDX_FOTO_SINGOLA = 3
        self.stack.addWidget(self.video_selector_page)    # IDX_VIDEO_SELECTOR = 4
        self.stack.addWidget(self.video_singolo_page)     # IDX_VIDEO_SINGOLO = 5
        self.stack.addWidget(self.video_stereo_page)       # IDX_VIDEO_STEREO = 6
        self.stack.addWidget(self.training_page)          # IDX_TRAINING = 7

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