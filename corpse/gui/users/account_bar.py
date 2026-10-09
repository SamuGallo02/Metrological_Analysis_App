"""'User X (type) - online/offline   [Log out]' row to place at the top of the home."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QWidget

from common.i18n import tr
from common.qt_utils import run_async

from corpse.functions.users.session import Session
from .labels import role_label


class AccountBar(QFrame):
    logout_requested = Signal()
    profile_requested = Signal()

    def __init__(self, session: Session, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        self.label = QLabel()
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.btn_profile = QPushButton(tr("My profile"))
        self.btn_profile.clicked.connect(self.profile_requested.emit)
        self.btn_retry = QPushButton(tr("Reconnect"))
        self.btn_retry.clicked.connect(self._retry)
        self.btn_out = QPushButton()
        self.btn_out.clicked.connect(self.logout_requested.emit)
        lay.addWidget(self.label, 1)
        for b in (self.btn_profile, self.btn_retry, self.btn_out):
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

    def _retry(self) -> None:
        def done(ok: bool) -> None:
            self.refresh()
            if not ok:
                QMessageBox.information(self, tr("Server"), tr("The server is still unreachable."))
        run_async(self, self.session.reconnect, done)
