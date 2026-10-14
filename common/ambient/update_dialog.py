"""Updates window (check / update / repair the application's code) and the once-a-day offer at startup.

The work itself is done by `python -m common.ambient.updater` (stdlib only, in a windowless process);
this module only shows it."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)

from common.i18n import tr
from common.params import NO_WINDOW, PROGRESS_PREFIX
from common.ui.qt_utils import HiddenProcess, run_async

from .updater import config, manifest, prefs, versions

ROOT = Path(__file__).resolve().parents[2]


def restart_app(root: Path = ROOT) -> None:
    """Starts a fresh copy of the app (without update checks) and closes this one."""
    subprocess.Popen([sys.executable, str(Path(root) / "main.py"), "--no-update"], cwd=str(root), **NO_WINDOW)
    app = QApplication.instance()
    if app:
        app.quit()


class UpdateDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None, root: Path = ROOT, start_update: bool = False):
        super().__init__(parent)
        self.root = Path(root)
        self.setWindowTitle(tr("Updates"))
        self.setMinimumWidth(520)
        self._dev = versions.is_dev_checkout(self.root)
        self._busy = False
        lay = QVBoxLayout(self)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.hide()
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(300)
        self.log.setMinimumHeight(110)
        self.mode = QComboBox()
        self.mode.addItem(tr("Ask me when a new version is out"), "ask")
        self.mode.addItem(tr("Install new versions automatically"), "auto")
        self.mode.addItem(tr("Never check"), "off")
        self.mode.setCurrentIndex(config.MODES.index(prefs.mode(self.root)))
        self.mode.currentIndexChanged.connect(lambda _i: prefs.save(self.root, mode=self.mode.currentData()))
        row = QHBoxLayout()
        self.btn_check = QPushButton(tr("Check now"))
        self.btn_update = QPushButton(tr("Update now"))
        self.btn_repair = QPushButton(tr("Verify and repair files"))
        self.btn_close = QPushButton(tr("Close"))
        self.btn_check.clicked.connect(self.check)
        self.btn_update.clicked.connect(self.update_now)
        self.btn_repair.clicked.connect(self.repair)
        self.btn_close.clicked.connect(self.accept)
        for b in (self.btn_check, self.btn_update, self.btn_repair):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self.btn_close)
        for w in (self.info, self.mode, self.status, self.bar, self.log):
            lay.addWidget(w)
        lay.addLayout(row)
        self.proc = HiddenProcess(self)
        self.proc.line.connect(self._on_line)
        self.proc.failed.connect(lambda m: self._finish(1, m))
        self._on_done = None
        self.proc.done.connect(lambda code: self._finish(code))
        self._refresh_info()
        if self._dev:
            self.status.setText(tr("This folder is a git working copy: update it with git pull."))
            for b in (self.btn_check, self.btn_update, self.btn_repair, self.mode):
                b.setEnabled(False)
        elif start_update:
            self.update_now()

    # -- helpers -------------------------------------------------------------
    def _refresh_info(self) -> None:
        label = versions.installed_label(self.root) or tr("unknown")
        self.info.setText(tr("Installed version:") + f" <b>{label}</b>")

    def _run(self, args: List[str], on_done=None) -> None:
        if self._busy:
            return
        self._busy = True
        self._on_done = on_done
        for b in (self.btn_check, self.btn_update, self.btn_repair):
            b.setEnabled(False)
        self.log.clear()
        self.bar.setValue(0)
        self.bar.show()
        self.proc.start(sys.executable, ["-m", "common.ambient.updater", "--root", str(self.root)] + args, self.root)

    def _on_line(self, ln: str) -> None:
        if ln.startswith(PROGRESS_PREFIX):
            parts = ln.split(" ", 2)
            try:
                self.bar.setValue(int(float(parts[1])))
            except (IndexError, ValueError):
                pass
        elif ln:
            self.log.appendPlainText(ln)

    def _finish(self, code: int, msg: str = "") -> None:
        self._busy = False
        for b in (self.btn_check, self.btn_update, self.btn_repair):
            b.setEnabled(True)
        self.bar.hide()
        self._refresh_info()
        cb, self._on_done = self._on_done, None
        if msg:
            self.log.appendPlainText(msg)
        if cb:
            cb(code)

    # -- actions ---------------------------------------------------------------
    def check(self) -> None:
        self.status.setText(tr("Checking..."))
        found: List[str] = []
        self.proc.line.connect(found.append)

        def done(code: int) -> None:
            self.proc.line.disconnect(found.append)
            if code == 10:
                self.status.setText(tr("A new version is available."))
            elif code == 0:
                self.status.setText(tr("You have the latest version."))
            else:
                self.status.setText(tr("Could not check (is the internet connection working?)."))
        self._run(["check"], done)

    def update_now(self) -> None:
        self.status.setText(tr("Updating..."))

        def done(code: int) -> None:
            if code != 0:
                self.status.setText(tr("The update did not complete. Nothing was lost: try again later."))
                return
            self.status.setText(tr("Update completed."))
            if QMessageBox.question(self, tr("Updates"), tr("Restart the application now to use the new version?")
                                    ) == QMessageBox.StandardButton.Yes:
                restart_app(self.root)
        self._run(["update"], done)

    def repair(self) -> None:
        self.status.setText(tr("Verifying files..."))

        def done(code: int) -> None:
            self.status.setText(tr("All files are fine or were restored.") if code == 0
                                else tr("Some files could not be restored (is the internet connection working?)."))
        self._run(["repair", "--deep"], done)


def offer_update_later(window: QWidget, root: Path = ROOT) -> None:
    """In 'ask' mode, at most once a day: looks for a newer version in the background and, if there is one,
    asks whether to install it. Silent when offline."""
    try:
        if versions.is_dev_checkout(root) or prefs.mode(root) != "ask" or not prefs.check_due(root):
            return
        record = manifest.load(root)
    except OSError:
        return

    def fetch():
        return versions.latest(config.QUICK_TIMEOUT)

    def found(latest) -> None:
        prefs.mark_checked(root)
        if latest.sha == (record or {}).get("sha") or latest.sha == prefs.load(root).get("skip_sha"):
            return
        box = QMessageBox(window)
        box.setWindowTitle(tr("Updates"))
        box.setText(tr("A new version is available:") + f" {latest.label}\n\n"
                    + tr("Only the files that changed are downloaded."))
        update = box.addButton(tr("Update now"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("Later"), QMessageBox.ButtonRole.RejectRole)
        skip = box.addButton(tr("Skip this version"), QMessageBox.ButtonRole.DestructiveRole)
        box.exec()
        if box.clickedButton() is update:
            UpdateDialog(window, root, start_update=True).exec()
        elif box.clickedButton() is skip:
            prefs.save(root, skip_sha=latest.sha)

    run_async(window, fetch, found, lambda _e: None)
