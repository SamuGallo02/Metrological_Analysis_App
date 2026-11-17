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

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QPushButton, QScrollArea,
    QStackedWidget,
    QVBoxLayout, QWidget,
)

from corpse.gui.home.hub import AnalysisHub
from common.format import darker
from common.params import IMAGE_SUFFIXES, VIDEO_SUFFIXES
from common.ui.label_editor import edit_local_labels
from common.ui.layout import fit_to_screen, scrollable
from common.ui.widgets import ANALYSIS_COLOR, MenuCard, SERVER_COLOR, TRAINING_COLOR
from common.i18n import tr
from corpse.gui.analysis.analysis_gui import StereoAnalysisPage
from common.ui.widgets import set_manual_opener, set_performance_opener
from corpse.gui.manual.dialog import ManualDialog
from common.ui.layout import centered_content
from corpse.gui.analysis.photo_gui import PhotoAnalysisPage
from corpse.gui.analysis.video_gui import VideoAnalysisPage
from corpse.gui.analysis.video_stereo_gui import VideoStereoAnalysisPage
from corpse.gui.home.webcam_demo import WebcamDemoButton
from corpse.gui.training import TrainingPage
from corpse.functions.users.session import Session
from corpse.gui.home.performance import ModelPerformanceDialog
from corpse.gui.settings_dialog import SettingsDialog
from corpse.gui.users import AccountBar, AdminHome, FoldersPage, ProfilePage, ServerFoldersWidget



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
            cards.append((tr("Folders"), tr("The folders of this computer, those of the server and those of your "
                                            "work groups."), SERVER_COLOR, on_server))
        grid = QGridLayout()
        grid.setSpacing(20)
        for i, (label, description, color, cb) in enumerate(cards):
            grid.addWidget(MenuCard(label, description, color, onClick=cb), 0, i)
        layout.addLayout(centered_content(grid, max_width=960))
        layout.addStretch(2)


class AppWindow(QMainWindow):
    """Main window: account bar + QStackedWidget with all the sections."""

    closing = Signal()                              # main.py: this window is over (sign out, or the user closed it)

    def __init__(self, session: Session) -> None:
        set_manual_opener(lambda parent: ManualDialog(parent).exec())
        set_performance_opener(lambda parent: ModelPerformanceDialog(session, parent).exec())
        super().__init__()
        self.session = session
        self.setWindowTitle("Stereo Metrology Analysis — YOLO")
        self.sign_out_requested = False             # main.py: show the login again instead of closing
        self.setMinimumSize(1120, 720)              # room for the tables and the side panels;
        fit_to_screen(self, 1300, 850)              # fit_to_screen lowers it on a small screen
        self._load_app_icon()

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        self.account_bar = AccountBar(session)
        self.account_bar.logout_requested.connect(self._sign_out)
        self.account_bar.profile_requested.connect(self._open_profile)
        self.account_bar.settings_requested.connect(self._open_settings)
        root.addWidget(self.account_bar)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        # analysis and training pages (unchanged)
        self.stereo_page = StereoAnalysisPage(on_home=self._go_home)
        self.foto_singola_page = PhotoAnalysisPage(on_home=self._go_home)
        self.video_singolo_page = VideoAnalysisPage(on_home=self._go_home)
        self.video_stereo_page = VideoStereoAnalysisPage(on_home=self._go_home)
        self.training_page = TrainingPage(on_home=self._go_home, session=session)
        self.analysis_targets: Dict[str, QWidget] = {
            "photo": self.foto_singola_page, "photo_stereo": self.stereo_page,
            "video": self.video_singolo_page, "video_stereo": self.video_stereo_page,
        }

        # Analysis screen: the 4 analyses and, at the top, the webcam demo
        self.analysis_hub = AnalysisHub(on_home=self._go_home, demo=WebcamDemoButton())
        self.analysis_hub.labels_requested.connect(self._edit_labels)
        self.analysis_hub.performance_requested.connect(self._open_performance)
        self.analysis_hub.requested.connect(lambda aid: self.show_page(self.analysis_targets[aid]))

        # home based on the account type
        has_admin_screens = AdminHome is not None          # missing in the user edition
        if session.is_admin and has_admin_screens:
            self.home_page: QWidget = AdminHome(session, on_training=self._open_training,
                                                on_analysis=lambda: self.show_page(self.analysis_hub))
        else:
            self.home_page = HomePage(session, on_analysis=lambda: self.show_page(self.analysis_hub),
                                      on_training=self._open_training, on_server=self._open_server)

        if session.is_admin and has_admin_screens:
            self.account_bar.state_changed.connect(self.home_page.apply_state)
        self._holders: Dict[QWidget, QWidget] = {}      # every page lives inside its own scroll area
        for page in (self.home_page, self.analysis_hub, *self.analysis_targets.values(), self.training_page):
            self._holder(page)
        self._dynamic: Dict[str, QWidget] = {}          # pages recreated on every opening (profile, server)
        self.show_page(self.home_page)

    # ---- navigation ---------------------------------------------------------
    def _holder(self, page: QWidget) -> QWidget:
        """The scroll area a page is shown in: a page bigger than the window scrolls instead of forcing the
        window to grow (small screens, large system fonts)."""
        holder = self._holders.get(page)
        if holder is None:
            holder = scrollable(page)
            self._holders[page] = holder
            self.stack.addWidget(holder)
        return holder

    def show_page(self, page: QWidget) -> None:
        self.stack.setCurrentWidget(self._holder(page))

    def current_page(self) -> QWidget:
        """The page the user is looking at (not the scroll area around it)."""
        current = self.stack.currentWidget()
        return current.widget() if isinstance(current, QScrollArea) else current

    def _go_home(self) -> None:
        self.show_page(self.home_page)
        self.account_bar.refresh()

    def _open_training(self) -> None:
        """Training opens straight away: on the server it needs nothing. What has to be downloaded to train on
        this computer is asked for by the page itself, when that button is pressed."""
        self.show_page(self.training_page)

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

    def _edit_labels(self) -> None:
        """Picks a photo or video of this computer and opens the label editor on it."""
        patterns = " ".join(f"*{e}" for e in sorted(IMAGE_SUFFIXES + VIDEO_SUFFIXES))
        f, _ = QFileDialog.getOpenFileName(self, tr("Choose a photo or video"), "", f"{tr('Photos')} ({patterns})")
        if f:
            edit_local_labels(self, Path(f))

    def _open_performance(self) -> None:
        ModelPerformanceDialog(self.session, self).exec()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.session, self)
        dialog.server_changed.connect(self._sign_out)       # the account belonged to the old server
        dialog.exec()

    def _open_profile(self) -> None:
        self._show_dynamic("profile", ProfilePage(self.session))

    def _open_server(self) -> None:
        self._show_dynamic("folders", FoldersPage(self.session))

    def _sign_out(self) -> None:
        """Sign out, sign in without an account, or change server: goes back to the login screen WITHOUT restarting
        the application (the libraries stay loaded, so coming back takes no time). The window closes and main.py
        shows the login again and builds a new one."""
        self.sign_out_requested = True
        QTimer.singleShot(0, self._finish_sign_out)          # lets the dialog that asked for it close first

    def _finish_sign_out(self) -> None:
        # A dialog may still be open (settings, profile): it is closed first, otherwise its own event loop would
        # keep running and the application would stay with no window at all. main.py waits for `closing`, which
        # works from inside a dialog's loop too - unlike QApplication.quit(), that ends only the innermost one.
        for widget in QApplication.topLevelWidgets():
            if widget is not self and widget.isVisible():
                widget.close()
        self.session.logout()
        self.close()

    def closeEvent(self, event) -> None:
        super().closeEvent(event)
        self.closing.emit()

    def _load_app_icon(self) -> None:
        from common.paths import ICON_FILE
        icon_path = ICON_FILE
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
