"""Pagina del proprio profilo: dati personali, cartelle sul server e sul computer, lingua, password."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from common.i18n import tr, tr_error
from common.params import PROFILE_FIELDS
from common.qt_utils import run_async
from common.ui.language import LanguageWidget

from ..params import LOCAL_FOLDERS
from ..session import Session
from .browser import ServerBrowserWidget
from .labels import role_label


def _open_folder(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(path)                                      # noqa: S606
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])


class ProfilePage(QWidget):
    folders_changed = Signal()

    def __init__(self, session: Session, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<h2>{tr('My profile')}</h2>"))
        self.tabs = QTabWidget()
        self.tabs.addTab(self._personal(), tr("Personal data"))
        if not session.is_guest:
            self.tabs.addTab(ServerBrowserWidget(session, ("mine",)), tr("My folder on the server"))
        self.tabs.addTab(self._local(), tr("Folders on this computer"))
        self.tabs.addTab(LanguageWidget(), tr("Language"))
        lay.addWidget(self.tabs, 1)

    # ---- dati personali + password -------------------------------------------
    def _personal(self) -> QWidget:
        w, lay, s = QWidget(), QVBoxLayout(), self.session
        w.setLayout(lay)
        if s.is_guest:
            lay.addWidget(QLabel(tr("You are using the application without an account. Sign in to create a profile "
                                    "and to use your personal folder on the server.")))
            lay.addStretch(1)
            return w
        form = QFormLayout()
        form.addRow(tr("Username:"), QLabel(f"<b>{s.username}</b>"))
        form.addRow(tr("Type:"), QLabel(role_label(s.role)))
        self.fields: Dict[str, QWidget] = {}
        labels = {"full_name": tr("Full name:"), "email": tr("Email:"), "organization": tr("Organization:"),
                  "phone": tr("Phone:"), "bio": tr("About me:")}
        data = s.store.profile(s.username) if not s.online else s.user or {}
        for f in PROFILE_FIELDS:
            if f == "bio":
                e = QPlainTextEdit(data.get(f, ""))
                e.setMaximumHeight(90)
            else:
                e = QLineEdit(data.get(f, ""))
                e.setMaxLength(PROFILE_FIELDS[f])
            self.fields[f] = e
            form.addRow(labels[f], e)
        lay.addLayout(form)
        row = QHBoxLayout()
        self.btn_save = QPushButton(tr("Save profile"))
        self.btn_save.setEnabled(s.online)
        self.btn_save.clicked.connect(self._save)
        row.addStretch(1)
        row.addWidget(self.btn_save)
        lay.addLayout(row)
        self.msg = QLabel(tr("Your data is stored on the server and a copy is kept on this computer.") if s.online
                          else tr("You are offline: you can see your saved data, but not change it."))
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)

        box = QGroupBox(tr("Change password"))
        pf = QFormLayout(box)
        self.old, self.new, self.new2 = QLineEdit(), QLineEdit(), QLineEdit()
        for e in (self.old, self.new, self.new2):
            e.setEchoMode(QLineEdit.EchoMode.Password)
        pf.addRow(tr("Current password:"), self.old)
        pf.addRow(tr("New password:"), self.new)
        pf.addRow(tr("Repeat new password:"), self.new2)
        self.btn_pw = QPushButton(tr("Change password"))
        self.btn_pw.setEnabled(s.online)
        self.btn_pw.clicked.connect(self._password)
        pf.addRow(self.btn_pw)
        lay.addWidget(box)
        lay.addStretch(1)
        return w

    def _text(self, f: str) -> str:
        e = self.fields[f]
        return e.toPlainText() if isinstance(e, QPlainTextEdit) else e.text()

    def _save(self) -> None:
        values = {f: self._text(f) for f in PROFILE_FIELDS}
        run_async(self, lambda: self.session.save_profile(**values),
                  lambda _u: self.msg.setText(tr("Profile saved.")),
                  lambda e: QMessageBox.warning(self, tr("Error"), tr_error(e)))

    def _password(self) -> None:
        if self.new.text() != self.new2.text():
            return QMessageBox.warning(self, tr("Error"), tr("The two passwords do not match."))
        old, new = self.old.text(), self.new.text()

        def done(_r) -> None:
            self.old.clear(); self.new.clear(); self.new2.clear()
            self.msg.setText(tr("Password changed. Use the new one the next time you sign in."))

        run_async(self, lambda: self.session.client.change_password(old, new), done,
                  lambda e: QMessageBox.warning(self, tr("Error"), tr_error(e)))

    # ---- cartelle sul computer ------------------------------------------------
    def _local(self) -> QWidget:
        w, lay = QWidget(), QVBoxLayout()
        w.setLayout(lay)
        lay.addWidget(QLabel(tr("Choose the folders on this computer that are offered by default when you download from, or "
                                "upload to, the server.")))
        names = {"photos": tr("Photos"), "models": tr("YOLO models"), "datasets": tr("Datasets"), "results": tr("Results")}
        current = self.session.local_folders()
        self.local_edits: Dict[str, QLineEdit] = {}
        form = QFormLayout()
        for key in LOCAL_FOLDERS:
            edit = QLineEdit(current[key])
            self.local_edits[key] = edit
            row = QHBoxLayout()
            row.addWidget(edit, 1)
            b1, b2 = QPushButton(tr("Browse...")), QPushButton(tr("Open"))
            b1.clicked.connect(lambda _c=False, e=edit: self._browse(e))
            b2.clicked.connect(lambda _c=False, e=edit: _open_folder(e.text()))
            row.addWidget(b1)
            row.addWidget(b2)
            form.addRow(names[key] + ":", row)
        lay.addLayout(form)
        row = QHBoxLayout()
        row.addStretch(1)
        reset = QPushButton(tr("Restore defaults"))
        reset.clicked.connect(self._reset_folders)
        save = QPushButton(tr("Save folders"))
        save.clicked.connect(self._save_folders)
        row.addWidget(reset)
        row.addWidget(save)
        lay.addLayout(row)
        self.local_msg = QLabel("")
        lay.addWidget(self.local_msg)
        lay.addStretch(1)
        return w

    def _browse(self, edit: QLineEdit) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Choose a folder"), edit.text() or str(Path.home()))
        if d:
            edit.setText(d)

    def _owner(self) -> str:
        return "" if self.session.is_guest else self.session.username

    def _save_folders(self) -> None:
        folders = {k: e.text().strip() for k, e in self.local_edits.items()}
        for p in folders.values():
            try:
                Path(p).mkdir(parents=True, exist_ok=True)
            except OSError:
                return QMessageBox.warning(self, tr("Error"), tr("Cannot create the folder: {path}", path=p))
        self.session.store.set_folders(self._owner(), folders)
        self.local_msg.setText(tr("Folders saved."))
        self.folders_changed.emit()

    def _reset_folders(self) -> None:
        self.session.store.set_folders(self._owner(), {})
        for k, v in self.session.local_folders().items():
            self.local_edits[k].setText(v)
        self.local_msg.setText(tr("Default folders restored."))
        self.folders_changed.emit()
