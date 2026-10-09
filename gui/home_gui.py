"""
Modulo della Home Page e della Finestra Applicativa Principale.
Instrada l'utente verso le sezioni, tutte ospitate nella stessa finestra tramite QStackedWidget:
  * Home utente: Analisi (-> schermata con le 4 analisi e la demo), Training, Cartelle del server.
  * Home amministratore (ruolo "server"): Gestione (utenti, database, training); analisi in secondo piano.
  * Profilo personale, Manuale d'uso.
La barra account (utente, tipo, online/offline) sta sopra tutte le pagine.

Autore: Samuele Gallo
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Dict

from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from analysis.hub import AnalysisHub
from common.i18n import tr
from gui.analysis_gui import StereoAnalysisPage
from gui.common_widgets import ManualDialog
from gui.home_layout import centered_content
from gui.photo_gui import PhotoAnalysisPage
from gui.video_gui import VideoAnalysisPage
from gui.video_stereo_gui import VideoStereoAnalysisPage
from gui.webcam_demo import WebcamDemoButton
from training import TrainingPage
from training.setup_dialog import ensure_training_ready
from users.session import Session
from users.ui import AccountBar, AdminHome, ProfilePage, ServerBrowserWidget

ANALYSIS_COLOR, TRAINING_COLOR, SERVER_COLOR = "#1565c0", "#d84315", "#2e7d32"


class MenuCard(QFrame):
    """Scheda per ciascuna sezione, con titolo e descrizione ad andata a capo automatica."""

    def __init__(self, title: str, description: str, color: str, onClick=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.onClick = onClick
        self.setMinimumSize(280, 160)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{ background-color: {color}; border-radius: 10px; }}
            QFrame:hover {{ background-color: {color}dd; }}
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
    """Home dell'utente: Analisi, Training e (se ha un account) Cartelle del server."""

    def __init__(self, session: Session, on_analysis: Callable[[], None], on_training: Callable[[], None],
                 on_server: Callable[[], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        top_bar.addStretch(1)
        btn_manual = QPushButton(tr("User manual"))
        btn_manual.clicked.connect(lambda: ManualDialog(self).exec())
        top_bar.addWidget(btn_manual)
        layout.addLayout(top_bar)
        layout.addStretch(1)

        title = QLabel("Stereo Metrology Analysis")
        title.setStyleSheet("font-size: 26px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        subtitle = QLabel(tr("Choose what you want to do"))
        subtitle.setStyleSheet("font-size: 14px; color: #888888;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        layout.addSpacing(30)

        cards = [
            (tr("Analysis"), tr("Detection, tracking and real measurements on photos and videos, single or stereo."),
             ANALYSIS_COLOR, on_analysis),
            (tr("Training"), tr("Train a new YOLO model on an annotated dataset."), TRAINING_COLOR, on_training),
        ]
        if not session.is_guest:
            cards.append((tr("Server folders"), tr("Look at and donate photos, download and upload YOLO models and datasets."),
                          SERVER_COLOR, on_server))
        grid = QGridLayout()
        grid.setSpacing(20)
        for i, (label, description, color, cb) in enumerate(cards):
            grid.addWidget(MenuCard(label, description, color, onClick=cb), 0, i)
        layout.addLayout(centered_content(grid, max_width=960))
        layout.addStretch(2)


class AppWindow(QMainWindow):
    """Finestra principale: barra account + QStackedWidget con tutte le sezioni."""

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.setWindowTitle("Stereo Metrology Analysis — YOLO")
        self.setMinimumSize(1300, 850)
        self._load_app_icon()

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        self.account_bar = AccountBar(session)
        self.account_bar.logout_requested.connect(self._sign_out)
        self.account_bar.profile_requested.connect(self._open_profile)
        root.addWidget(self.account_bar)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        # pagine di analisi e training (invariate)
        self.stereo_page = StereoAnalysisPage(on_home=self._go_home)
        self.foto_singola_page = PhotoAnalysisPage(on_home=self._go_home)
        self.video_singolo_page = VideoAnalysisPage(on_home=self._go_home)
        self.video_stereo_page = VideoStereoAnalysisPage(on_home=self._go_home)
        self.training_page = TrainingPage(on_home=self._go_home)
        self.analysis_targets: Dict[str, QWidget] = {
            "photo": self.foto_singola_page, "photo_stereo": self.stereo_page,
            "video": self.video_singolo_page, "video_stereo": self.video_stereo_page,
        }

        # schermata Analisi: le 4 analisi e, in alto, la demo webcam
        self.analysis_hub = AnalysisHub(on_home=self._go_home, demo=WebcamDemoButton())
        self.analysis_hub.requested.connect(lambda aid: self.stack.setCurrentWidget(self.analysis_targets[aid]))

        # home in base al tipo di account
        if session.is_admin:
            self.home_page: QWidget = AdminHome(session, on_training=self._open_training,
                                                on_analysis=lambda: self.stack.setCurrentWidget(self.analysis_hub))
        else:
            self.home_page = HomePage(session, on_analysis=lambda: self.stack.setCurrentWidget(self.analysis_hub),
                                      on_training=self._open_training, on_server=self._open_server)

        for page in (self.home_page, self.analysis_hub, *self.analysis_targets.values(), self.training_page):
            self.stack.addWidget(page)
        self._dynamic: Dict[str, QWidget] = {}          # pagine ricreate a ogni apertura (profilo, server)
        self.stack.setCurrentWidget(self.home_page)

    # ---- navigazione ---------------------------------------------------------
    def _go_home(self) -> None:
        self.stack.setCurrentWidget(self.home_page)
        self.account_bar.refresh()

    def _open_training(self) -> None:
        """Avvisa e installa le estensioni mancanti (con barra di avanzamento), poi apre il training."""
        if ensure_training_ready(self):
            self.stack.setCurrentWidget(self.training_page)

    def _show_dynamic(self, key: str, widget: QWidget) -> None:
        old = self._dynamic.pop(key, None)
        if old is not None:
            self.stack.removeWidget(old)
            old.deleteLater()
        holder = QWidget()
        lay = QVBoxLayout(holder)
        bar = QHBoxLayout()
        back = QPushButton(tr("← Back to home"))
        back.clicked.connect(self._go_home)
        bar.addWidget(back)
        bar.addStretch(1)
        lay.addLayout(bar)
        lay.addWidget(widget, 1)
        self._dynamic[key] = holder
        self.stack.addWidget(holder)
        self.stack.setCurrentWidget(holder)

    def _open_profile(self) -> None:
        self._show_dynamic("profile", ProfilePage(self.session))

    def _open_server(self) -> None:
        self._show_dynamic("server", ServerBrowserWidget(self.session))

    def _sign_out(self) -> None:
        """Esci (o, senza account, vai all'accesso): chiude la sessione e riavvia l'app sulla schermata di accesso."""
        self.session.logout()
        QProcess.startDetached(sys.executable, sys.argv)
        QApplication.quit()

    def _load_app_icon(self) -> None:
        base_dir = Path(__file__).parent.parent / "assets"
        icon_path = base_dir / "app_icon.ico"
        if not icon_path.exists():
            icon_path = base_dir / "app_icon.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
