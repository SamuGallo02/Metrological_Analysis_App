"""Login / registration, with optional access key and no-account mode."""
from __future__ import annotations

import os
import re
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTabBar, QVBoxLayout, QWidget)

from common.i18n import tr, tr_error
from common.params import DEFAULT_SERVER_URL
from common.ui.language import LanguageButton
from common.ui.qt_utils import run_async

from corpse.functions.users.api import OfflineError
from corpse.functions.users.session import Session


def server_address() -> str:
    """Server to connect to: AM_SERVER_URL if set, else the address in the global parameters, else the last used."""
    return os.environ.get("AM_SERVER_URL", "").strip() or DEFAULT_SERVER_URL


def _mmss(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


class LoginDialog(QDialog):
    """Log in / Register. If the server does not respond, allows offline access (already known users)."""

    def __init__(self, session: Session, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle(tr("Sign in"))
        self.setMinimumSize(860, 540)
        self.resize(1040, 640)              # size when restored from full screen
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)   # maximize/restore button
        self.mode = "online"
        self._wait = 0                      # remaining lockout seconds
        self._wait_scope = ""

        # Opening page: introduction on the left, login card in the center-right
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 0)
        top = QHBoxLayout()
        top.addStretch(1)
        top.addWidget(LanguageButton())              # language can be changed before signing in
        outer.addLayout(top)
        page = QHBoxLayout()
        outer.addLayout(page, 1)
        page.setContentsMargins(32, 8, 32, 32)
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
        # The server address is not asked: it comes from the global parameters (or AM_SERVER_URL). The field is only a
        # holder that is never shown.
        self.url = QLineEdit(server_address())
        self.user = QLineEdit(session.store.settings().get("last_user", ""))
        self.email = QLineEdit()
        self.email.setPlaceholderText("name@example.com")
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw2 = QLineEdit()
        self.pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText(tr("administrators only (optional)"))
        self.key.setToolTip(tr("With the access key you become a permanent administrator of the server, even remotely."))
        form.addRow(tr("Username:"), self.user)
        self.email_label = QLabel(tr("Email:"))
        form.addRow(self.email_label, self.email)
        form.addRow(tr("Password:"), self.pw)
        self.pw2_label = QLabel(tr("Repeat password:"))
        form.addRow(self.pw2_label, self.pw2)
        self.key_label = QLabel(tr("Access key:"))
        form.addRow(self.key_label, self.key)
        lay.addLayout(form)
        self.btn_key = QPushButton(tr("I have an access key (administrators)"))
        self.btn_key.setFlat(True)
        self.btn_key.setCheckable(True)
        self.btn_key.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_key.toggled.connect(self._show_key)
        lay.addWidget(self.btn_key, 0, Qt.AlignmentFlag.AlignLeft)
        self._show_key(False)

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

    # ---- state -------------------------------------------------------------
    def _tab(self, i: int) -> None:
        reg = i == 1
        self.pw2.setVisible(reg)
        self.pw2_label.setVisible(reg)
        self.email.setVisible(reg)
        self.email_label.setVisible(reg)
        self.btn_ok.setText(tr("Register") if reg else tr("Sign in"))
        self._info(tr("New accounts are 'User' accounts; with the access key the account becomes a 'Server' "
                      "(administrator) account.") if reg else
                   tr("With the access key you become a permanent administrator of the server."))

    def _show_key(self, shown: bool) -> None:
        self.key.setVisible(shown)
        self.key_label.setVisible(shown)
        self.btn_key.setVisible(not shown)

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

    # ---- temporary lockout: countdown, everything else keeps working ----
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

    # ---- actions ------------------------------------------------------------
    def _offline(self) -> None:
        self.session.start_offline()
        self.mode = "guest"
        self.accept()

    def _submit(self) -> None:
        url, user, pw, key = (self.url.text().strip(), self.user.text().strip(), self.pw.text(),
                              self.key.text().strip())
        email = self.email.text().strip()
        if not url:
            return self._error(tr("No server is configured."))
        if not user or not pw:
            return self._error(tr("Fill in username and password."))
        reg = self.tabs.currentIndex() == 1
        if reg and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return self._error(tr("Enter a valid email address."))
        if reg and pw != self.pw2.text():
            return self._error(tr("The two passwords do not match."))
        if key and not self.btn_key.isHidden():
            self._show_key(True)
        self._set_busy(True)

        def job():
            if reg:
                self.session.register(user, pw, url, key, email)
            return self.session.login(user, pw, url, key=key)

        def ok(mode: str) -> None:
            self.mode = mode
            self.accept()

        def fail(e: Exception) -> None:
            if getattr(e, "status", 0) == 429 and getattr(e, "retry_after", 0):
                self._set_busy(False)
                return self._start_wait(int(e.retry_after), e.params.get("scope", "account"))
            text = tr_error(e)
            self._error(text + " " + tr("Check your connection and try again.") if isinstance(e, OfflineError) else text)

        run_async(self, job, ok, fail)
