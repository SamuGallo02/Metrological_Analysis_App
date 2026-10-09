"""
Home Page and Main Application Window Module.
Routes the user to the sections, all hosted in the same window through a QStackedWidget:
  * User home: Analysis (-> screen with the 4 analyses and the demo), Training, Server folders.
  * Administrator home ("server" role): Management (users, database, training); analysis in the background.
  * Personal profile, User manual.
The account bar (user, type, online/offline) sits above all pages.

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

from corpse.gui.home.hub import AnalysisHub
from common.format import darker
from common.i18n import tr
from corpse.gui.analysis.analysis_gui import StereoAnalysisPage
from common.ui.widgets import set_manual_opener
from corpse.gui.manual.dialog import ManualDialog
from common.ui.layout import centered_content
from corpse.gui.analysis.photo_gui import PhotoAnalysisPage
from corpse.gui.analysis.video_gui import VideoAnalysisPage
from corpse.gui.analysis.video_stereo_gui import VideoStereoAnalysisPage
from corpse.gui.home.webcam_demo import WebcamDemoButton
from corpse.gui.training import TrainingPage
from corpse.gui.training.setup_dialog import ensure_training_ready
from corpse.functions.users.session import Session
from corpse.gui.users import AccountBar, AdminHome, ProfilePage, ServerBrowserWidget

ANALYSIS_COLOR, TRAINING_COLOR, SERVER_COLOR = "#1565c0", "#d84315", "#2e7d32"


class MenuCard(QFrame):
    """Card for each section, with a title and an automatically wrapping description."""

    def __init__(self, title: str, description: str, color: str, onClick=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.onClick = onClick
        self.setMinimumSize(280, 160)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{ background-color: {color}; border-radius: 10px; }}
            QFrame:hover {{ background-color: {darker(color)}; }}
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
    """User home: Analysis, Training and (if they have an account) Server folders."""

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
    """Main window: account bar + QStackedWidget with all the sections."""

    def __init__(self, session: Session) -> None:
        set_manual_opener(lambda parent: ManualDialog(parent).exec())
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

        # analysis and training pages (unchanged)
        self.stereo_page = StereoAnalysisPage(on_home=self._go_home)
        self.foto_singola_page = PhotoAnalysisPage(on_home=self._go_home)
        self.video_singolo_page = VideoAnalysisPage(on_home=self._go_home)
        self.video_stereo_page = VideoStereoAnalysisPage(on_home=self._go_home)
        self.training_page = TrainingPage(on_home=self._go_home)
        self.analysis_targets: Dict[str, QWidget] = {
            "photo": self.foto_singola_page, "photo_stereo": self.stereo_page,
            "video": self.video_singolo_page, "video_stereo": self.video_stereo_page,
        }

        # Analysis screen: the 4 analyses and, at the top, the webcam demo
        self.analysis_hub = AnalysisHub(on_home=self._go_home, demo=WebcamDemoButton())
        self.analysis_hub.requested.connect(lambda aid: self.stack.setCurrentWidget(self.analysis_targets[aid]))

        # home based on the account type
        if session.is_admin:
            self.home_page: QWidget = AdminHome(session, on_training=self._open_training,
                                                on_analysis=lambda: self.stack.setCurrentWidget(self.analysis_hub))
        else:
            self.home_page = HomePage(session, on_analysis=lambda: self.stack.setCurrentWidget(self.analysis_hub),
                                      on_training=self._open_training, on_server=self._open_server)

        if session.is_admin:
            self.account_bar.state_changed.connect(self.home_page.apply_state)
        for page in (self.home_page, self.analysis_hub, *self.analysis_targets.values(), self.training_page):
            self.stack.addWidget(page)
        self._dynamic: Dict[str, QWidget] = {}          # pages recreated on every opening (profile, server)
        self.stack.setCurrentWidget(self.home_page)

    # ---- navigation ---------------------------------------------------------
    def _go_home(self) -> None:
        self.stack.setCurrentWidget(self.home_page)
        self.account_bar.refresh()

    def _open_training(self) -> None:
        """Warns and installs the missing extensions (with a progress bar), then opens training."""
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
        """Log out (or, without an account, go to login): closes the session and restarts the app on the login screen."""
        self.session.logout()
        QProcess.startDetached(sys.executable, sys.argv)
        QApplication.quit()

    def _load_app_icon(self) -> None:
        from common.paths import ICON_FILE
        icon_path = ICON_FILE
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
