"""Accesso / registrazione, con chiave di accesso facoltativa e modo senza account."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTabBar, QVBoxLayout, QWidget)

from common.i18n import tr, tr_error
from common.params import DEFAULT_SERVER_URL
from common.qt_utils import run_async

from ..api import OfflineError
from ..session import Session


def _mmss(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


class LoginDialog(QDialog):
    """Accedi / Registrati. Se il server non risponde permette l'accesso offline (utenti gia' visti)."""

    def __init__(self, session: Session, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle(tr("Sign in"))
        self.setMinimumSize(900, 520)
        self.mode = "online"
        self._wait = 0                      # secondi di blocco residui
        self._wait_scope = ""

        # Pagina di apertura: presentazione a sinistra, scheda di accesso al centro-destra
        page = QHBoxLayout(self)
        page.setContentsMargins(48, 32, 48, 32)
        page.setSpacing(56)
        page.addStretch(1)
        hero = QVBoxLayout()
        hero.addStretch(1)
        title = QLabel("Metrological Analysis")
        title.setStyleSheet("font-size: 34px; font-weight: 700;")
        title.setWordWrap(True)
        tagline = QLabel(tr("Stereo-photogrammetric measurement of objects with YOLO"))
        tagline.setStyleSheet("font-size: 17px; color: #9aa4b2;")
        tagline.setWordWrap(True)
        hero.addWidget(title)
        hero.addWidget(tagline)
        hero.addSpacing(18)
        for text in (tr("Measure length, width and height from stereo pairs"),
                     tr("Train your own YOLO models"),
                     tr("Share photos, models and datasets with your team")):
            item = QLabel("\u2022  " + text)
            item.setStyleSheet("font-size: 14px;")
            item.setWordWrap(True)
            hero.addWidget(item)
        hero.addStretch(1)
        hero_box = QWidget()
        hero_box.setLayout(hero)
        hero_box.setMinimumWidth(380)
        hero_box.setMaximumWidth(460)
        page.addWidget(hero_box, 1)
        card = QFrame()
        card.setObjectName("loginCard")
        card.setStyleSheet("#loginCard { border: 1px solid #3a4150; border-radius: 12px; }")
        card.setMinimumWidth(420)
        card.setMaximumWidth(480)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(24, 20, 24, 20)
        page.addWidget(card, 1, Qt.AlignmentFlag.AlignVCenter)
        page.addStretch(1)
        self.tabs = QTabBar()
        self.tabs.addTab(tr("Sign in"))
        self.tabs.addTab(tr("Register"))
        self.tabs.currentChanged.connect(self._tab)
        lay.addWidget(self.tabs)

        form = QFormLayout()
        self.url = QLineEdit(session.server_url or DEFAULT_SERVER_URL)
        self.url.setPlaceholderText("https://server.example.com")
        self.user = QLineEdit(session.store.settings().get("last_user", ""))
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw2 = QLineEdit()
        self.pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText(tr("administrators only (optional)"))
        self.key.setToolTip(tr("With the access key you become a permanent administrator of the server, even remotely."))
        form.addRow(tr("Server:"), self.url)
        form.addRow(tr("Username:"), self.user)
        form.addRow(tr("Password:"), self.pw)
        self.pw2_label = QLabel(tr("Repeat password:"))
        form.addRow(self.pw2_label, self.pw2)
        form.addRow(tr("Access key:"), self.key)
        lay.addLayout(form)

        self.msg = QLabel("")
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)
        row = QHBoxLayout()
        self.btn_ok = QPushButton(tr("Sign in"))
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self._submit)
        btn_cancel = QPushButton(tr("Quit"))
        btn_cancel.clicked.connect(self.reject)
        self.btn_offline = QPushButton(tr("Continue without signing in (offline)"))
        self.btn_offline.setToolTip(tr("Use analysis and training without an account: no server folders."))
        self.btn_offline.clicked.connect(self._offline)
        row.addWidget(btn_cancel)
        row.addStretch(1)
        row.addWidget(self.btn_ok)
        lay.addLayout(row)
        lay.addWidget(self.btn_offline)
        self.pw.returnPressed.connect(self._submit)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self._tab(0)

    # ---- stato -------------------------------------------------------------
    def _tab(self, i: int) -> None:
        reg = i == 1
        self.pw2.setVisible(reg)
        self.pw2_label.setVisible(reg)
        self.btn_ok.setText(tr("Register") if reg else tr("Sign in"))
        self._info(tr("New accounts are 'User' accounts; with the access key the account becomes a 'Server' "
                      "(administrator) account.") if reg else
                   tr("With the access key you become a permanent administrator of the server."))

    def _info(self, text: str) -> None:
        self.msg.setStyleSheet("")
        self.msg.setText(text)

    def _set_busy(self, busy: bool) -> None:
        self.btn_ok.setEnabled(not busy and not (self._wait and self._wait_scope == "account"))
        self.btn_offline.setEnabled(not busy)
        if busy:
            self._info(tr("Connecting..."))

    def _error(self, text: str) -> None:
        self._set_busy(False)
        self.msg.setStyleSheet("color: #e57373;")
        self.msg.setText(text)

    # ---- blocco temporaneo: conto alla rovescia, il resto continua a funzionare ----
    def _start_wait(self, seconds: int, scope: str) -> None:
        self._wait, self._wait_scope = seconds, scope
        if scope == "key":
            self.key.clear()
            self.key.setEnabled(False)
        else:
            self.btn_ok.setEnabled(False)
        self.timer.start()
        self._tick(first=True)

    def _tick(self, first: bool = False) -> None:
        if not first:
            self._wait -= 1
        if self._wait <= 0:
            self.timer.stop()
            self.key.setEnabled(True)
            self.key.setPlaceholderText(tr("administrators only (optional)"))
            self.btn_ok.setEnabled(True)
            self._info("")
            self._wait_scope = ""
            return
        if self._wait_scope == "key":
            self.key.setPlaceholderText(tr("locked: {time}", time=_mmss(self._wait)))
            self.msg.setStyleSheet("color: #e57373;")
            self.msg.setText(tr("Too many wrong access keys. The key is locked for {time}: you can still sign in "
                                "without it.", time=_mmss(self._wait)))
        else:
            self.msg.setStyleSheet("color: #e57373;")
            self.msg.setText(tr("Too many attempts. Try again in {time}.", time=_mmss(self._wait)))

    # ---- azioni ------------------------------------------------------------
    def _offline(self) -> None:
        self.session.start_offline()
        self.mode = "guest"
        self.accept()

    def _submit(self) -> None:
        url, user, pw, key = (self.url.text().strip(), self.user.text().strip(), self.pw.text(),
                              self.key.text().strip())
        if not url or not user or not pw:
            return self._error(tr("Fill in server, username and password."))
        reg = self.tabs.currentIndex() == 1
        if reg and pw != self.pw2.text():
            return self._error(tr("The two passwords do not match."))
        self._set_busy(True)

        def job():
            if reg:
                self.session.register(user, pw, url, key)
            return self.session.login(user, pw, url, key=key)

        def ok(mode: str) -> None:
            self.mode = mode
            self.accept()

        def fail(e: Exception) -> None:
            if getattr(e, "status", 0) == 429 and getattr(e, "retry_after", 0):
                self._set_busy(False)
                return self._start_wait(int(e.retry_after), e.params.get("scope", "account"))
            text = tr_error(e)
            self._error(text + " " + tr("Check the address and your connection.") if isinstance(e, OfflineError) else text)

        run_async(self, job, ok, fail)
