"""Settings window: language, server address, updates and optional components, all in one place."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton, QTabWidget,
                               QVBoxLayout, QWidget)

from common.ambient.update_dialog import UpdatesPanel
from common.i18n import tr, tr_error
from common.ui.language import LanguageWidget
from common.ui.qt_utils import run_async

from corpse.functions.users.api import ApiClient, ApiError, normalize_url
from corpse.functions.users.session import Session
from corpse.gui.training.components import HardwareAccelerationWidget


class ServerPanel(QWidget):
    """Address of the server this app connects to."""

    changed = Signal()                     # the address changed: the account belongs to the old server

    def __init__(self, session: Session, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        lay = QVBoxLayout(self)
        self.address = QLabel()
        self.address.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        hint = QLabel(tr("Change the server this app connects to."))
        hint.setWordWrap(True)
        self.btn_change = QPushButton(tr("Server address"))
        self.btn_change.clicked.connect(self._change_server)
        lay.addWidget(hint)
        lay.addWidget(self.address)
        lay.addWidget(self.btn_change, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addStretch(1)
        self.refresh()

    def refresh(self) -> None:
        self.address.setText(f"<b>{self.session.server_url or tr('not set')}</b>")

    def _change_server(self) -> None:
        text, ok = QInputDialog.getText(
            self, tr("Server address"),
            tr("Address of the server, for example http://192.168.1.27:8765 or https://name.example.org."),
            text=self.session.server_url or "")
        if not ok or not text.strip():
            return
        try:
            url = normalize_url(text)
        except ApiError as e:
            return QMessageBox.warning(self, tr("Server"), tr_error(e))
        if url == self.session.server_url:
            return

        def reachable(_h) -> None:
            self._apply_server(url)

        def unreachable(_e: Exception) -> None:
            if QMessageBox.question(self, tr("Server"), tr("The server does not answer at this address. Use it anyway?")) \
                    == QMessageBox.StandardButton.Yes:
                self._apply_server(url)

        run_async(self, ApiClient(url).health, reachable, unreachable)

    def _apply_server(self, url: str) -> None:
        """Saves the address and signs out: the account belongs to the previous server."""
        self.session.store.update_settings(server_url=url)
        QMessageBox.information(self, tr("Server"), tr("Server address saved. Sign in again to use it."))
        self.refresh()
        self.changed.emit()


class SettingsDialog(QDialog):
    server_changed = Signal()

    def __init__(self, session: Session, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle(tr("Settings"))
        self.setMinimumSize(640, 480)
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.language = LanguageWidget()
        self.server = ServerPanel(session)
        self.server.changed.connect(self._on_server_changed)
        self.updates = UpdatesPanel()
        self.components = HardwareAccelerationWidget(self)
        self.tabs.addTab(self.language, tr("Language"))
        self.tabs.addTab(self.server, tr("Server"))
        self.tabs.addTab(self.updates, tr("Updates"))
        self.tabs.addTab(self.components, tr("Optional components"))
        lay.addWidget(self.tabs, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

    def _on_server_changed(self) -> None:
        self.server_changed.emit()
        self.accept()
