"""'User X (type) - online/offline   [Log out]' row to place at the top of the home."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton, QWidget

from common.i18n import tr, tr_error
from common.ui.language import LanguageButton
from common.ui.qt_utils import run_async

from corpse.functions.users.api import ApiClient, ApiError, normalize_url
from corpse.functions.users.session import Session
from .labels import role_label


class AccountBar(QFrame):
    logout_requested = Signal()
    profile_requested = Signal()
    state_changed = Signal()               # online/offline changed (after a successful reconnect)

    def __init__(self, session: Session, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        self.label = QLabel()
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.btn_profile = QPushButton(tr("My profile"))
        self.btn_profile.clicked.connect(self.profile_requested.emit)
        self.btn_server = QPushButton(tr("Server address"))
        self.btn_server.setToolTip(tr("Change the server this app connects to."))
        self.btn_server.clicked.connect(self._change_server)
        self.btn_updates = QPushButton(tr("Updates"))
        self.btn_updates.setToolTip(tr("Check for a new version, update the app or repair its files."))
        self.btn_updates.clicked.connect(self._open_updates)
        self.btn_retry = QPushButton(tr("Reconnect"))
        self.btn_retry.clicked.connect(self._retry)
        self.btn_out = QPushButton()
        self.btn_out.clicked.connect(self.logout_requested.emit)
        lay.addWidget(self.label, 1)
        lay.addWidget(LanguageButton())
        for b in (self.btn_profile, self.btn_server, self.btn_updates, self.btn_retry, self.btn_out):
            lay.addWidget(b)
        self.refresh()

    def refresh(self) -> None:
        s = self.session
        state = f"<font color='#66bb6a'>{tr('online')}</font>" if s.online else f"<font color='#ffa726'>{tr('offline')}</font>"
        if s.is_guest:
            self.label.setText(f"<b>{tr('No account')}</b> &middot; {state}")
        else:
            self.label.setText(f"<b>{s.username}</b> &middot; {role_label(s.role)} &middot; {state}")
        self.btn_retry.setVisible(not s.online and not s.is_guest)
        self.btn_out.setText(tr("Sign in") if s.is_guest else tr("Sign out"))

    def _open_updates(self) -> None:
        from common.ambient.update_dialog import UpdateDialog
        UpdateDialog(self).exec()

    def _retry(self) -> None:
        def done(ok: bool) -> None:
            self.refresh()
            self.state_changed.emit()
            if not ok:
                QMessageBox.information(self, tr("Server"), tr("The server is still unreachable."))
        run_async(self, self.session.reconnect, done)

    # ---- server address (typed by hand; temporary measure) -------------------
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
        """Saves the address and signs out: the account belongs to the previous server, the login page proposes the new one."""
        self.session.store.update_settings(server_url=url)
        QMessageBox.information(self, tr("Server"), tr("Server address saved. Sign in again to use it."))
        self.logout_requested.emit()
