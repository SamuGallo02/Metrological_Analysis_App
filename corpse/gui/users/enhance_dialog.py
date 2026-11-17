"""Improvement of a photo or a video asked of the server, from the first click to the file on disk.

The dialog sends the file, follows the queue and, when the improved copy comes back, asks the only question that
is left: add it beside the original, or put it in its place.

Autore: Samuele Gallo
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QRadioButton, QVBoxLayout, QWidget)

from common.errors import AppError
from common.i18n import tr, tr_error
from common.ui.qt_utils import run_async

from corpse.functions.users import enhance
from corpse.functions.users.session import Session

POLL_MS = 3000


class EnhanceDialog(QDialog):
    """Sends one file to the server, waits for the improved copy and keeps it where the user wants it."""

    def __init__(self, session: Session, media: Path, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        self.media = Path(media)
        self.job: Dict[str, Any] = {}
        self.improved: Optional[Path] = None
        self.kept: Optional[Path] = None
        self.setWindowTitle(tr("Improve with the server"))
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<b>{self.media.name}</b>"))
        self.status = QLabel(tr("Sending the file..."))
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self.choice = QWidget()
        choice_lay = QVBoxLayout(self.choice)
        choice_lay.setContentsMargins(0, 0, 0, 0)
        choice_lay.addWidget(QLabel(tr("What do you want to do with the improved file?")))
        self.add = QRadioButton(tr("Add it beside the original (enhanced folder)"))
        self.add.setChecked(True)
        self.replace = QRadioButton(tr("Put it in place of the original (a copy stays in 'originals')"))
        choice_lay.addWidget(self.add)
        choice_lay.addWidget(self.replace)
        self.choice.setVisible(False)
        lay.addWidget(self.choice)

        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_apply = QPushButton(tr("Apply"))
        self.btn_apply.setVisible(False)
        self.btn_apply.clicked.connect(self._apply)
        row.addWidget(self.btn_apply)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.buttons.rejected.connect(self._cancel)
        row.addWidget(self.buttons)
        lay.addLayout(row)

        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self._poll)
        QTimer.singleShot(0, self._start)

    # ---- the queue -----------------------------------------------------
    def _fail(self, error: Exception) -> None:
        self.timer.stop()
        self.status.setText(tr_error(error) if isinstance(error, AppError) else str(error))

    def _start(self) -> None:
        run_async(self, lambda: enhance.send(self.session.client, self.media), self._sent, self._fail)

    def _sent(self, job: Dict[str, Any]) -> None:
        self.job = job
        self.status.setText(tr("Waiting for a computer that can do it..."))
        self.timer.start()

    def _poll(self) -> None:
        if not self.job:
            return
        self.timer.stop()
        run_async(self, lambda: enhance.state(self.session.client, self.job), self._state, self._fail)

    def _state(self, job: Dict[str, Any]) -> None:
        self.job = job
        if enhance.done(job):
            self.status.setText(tr("Bringing the improved file back..."))
            run_async(self, self._download, self._ready, self._fail)
            return
        if enhance.failed(job):
            return self.status.setText(tr("The improvement did not work: {msg}", msg=job.get("message", "")))
        if not enhance.waiting(job):
            return self.status.setText(tr("The improvement was cancelled."))
        self.status.setText(tr("Working on it...") if job.get("status") == "running"
                            else tr("Waiting for a computer that can do it..."))
        self.timer.start()

    def _download(self) -> Path:
        folder = Path(tempfile.mkdtemp(prefix="enhanced_"))
        return enhance.collect(self.session.client, self.job, folder)

    def _ready(self, path: Path) -> None:
        self.improved = path
        self.status.setText(tr("The improved file is ready."))
        self.choice.setVisible(True)
        self.btn_apply.setVisible(True)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Not now"))

    # ---- the choice ----------------------------------------------------
    def _apply(self) -> None:
        if self.improved is None:
            return
        how = enhance.REPLACE if self.replace.isChecked() else enhance.ADD
        try:
            self.kept = enhance.keep(self.media, self.improved, how)
        except OSError as e:
            return self._fail(e)
        enhance.cleanup(self.session.client, self.job)
        self.accept()

    def _cancel(self) -> None:
        self.timer.stop()
        if self.job and enhance.waiting(self.job):
            try:
                self.session.client.cancel_enhance(self.job["id"])
            except Exception:                              # noqa: BLE001 - already started: it simply goes on
                pass
        self.reject()


def improve_with_server(parent: Optional[QWidget], session: Session, media: Path) -> Optional[Path]:
    """Opens the dialog; returns the file that was kept, or None."""
    if not getattr(session, "online", False):
        QMessageBox.information(parent, tr("Improve with the server"),
                                tr("Connect to the server to ask for the improvement."))
        return None
    dialog = EnhanceDialog(session, media, parent)
    return dialog.kept if dialog.exec() == QDialog.DialogCode.Accepted else None
