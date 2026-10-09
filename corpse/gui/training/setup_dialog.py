""""Train" button: warns that extensions are required and, if the user accepts, installs them automatically
showing a progress bar.

    from corpse.gui.training.setup_dialog import ensure_training_ready
    if ensure_training_ready(self):      # True = training can proceed right away
        ...open the training page...

Two cases, decided by core.environment_manager.get_cuda_status():
  * light extras only (a few MB): full installation in the window, then proceed.
  * PyTorch with GPU support (a few GB): the window DOWNLOADS everything with the bar (the app stays open);
    then the app restarts by itself to replace PyTorch (files are locked while the app is open) and the
    detached install process finishes within moments thanks to the already downloaded files.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)

from common.i18n import tr
from common.ui.qt_utils import HiddenProcess

from corpse.functions.training.params import INSTALL_COMPONENT, PROGRESS_PREFIX, WARN_PREFIX


def _python() -> str:
    from common.ambient.installer import state                       # app installer modules (late import)
    from common.ambient.installer.sysinfo import detect_system
    py = state.venv_python(detect_system().os_name)
    return str(py if Path(py).exists() else sys.executable)


class TrainingSetupDialog(QDialog):
    """Phase 1: notice and confirmation. Phase 2: progress bar."""

    def __init__(self, status: dict, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Components for training"))
        self.setMinimumWidth(480)
        self.heavy = bool(status["install_needed"])
        self.proc: Optional[HiddenProcess] = None
        self.ok = False

        lay = QVBoxLayout(self)
        if self.heavy:
            what = tr("<b>PyTorch with GPU support</b> ({variant}, a download of several GB) to use your {gpu} card",
                      variant=status["install_variant"], gpu=status["gpu_name"] or "NVIDIA")
            after = tr("When it finishes, the application will <b>restart by itself</b> to complete the activation "
                       "(a few moments).")
        else:
            what = tr("<b>the extensions required for training</b> (a few MB)")
            after = tr("The application will not be closed.")
        self.info = QLabel(tr("To use training, {what} must be installed.", what=what) + "<br><br>" + after
                           + "<br><br>" + tr("Do you want to install them now? Stay connected to the internet."))
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.info)

        self.text = QLabel("")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setMinimumHeight(140)
        for w in (self.text, self.bar, self.log):
            w.hide()
            lay.addWidget(w)

        row = QHBoxLayout()
        self.btn_details = QPushButton(tr("Details"))
        self.btn_details.setCheckable(True)
        self.btn_details.toggled.connect(self.log.setVisible)
        self.btn_details.hide()
        self.btn_no = QPushButton(tr("Cancel"))
        self.btn_no.clicked.connect(self._cancel)
        self.btn_yes = QPushButton(tr("Install"))
        self.btn_yes.setDefault(True)
        self.btn_yes.clicked.connect(self._start)
        row.addWidget(self.btn_details)
        row.addStretch(1)
        row.addWidget(self.btn_no)
        row.addWidget(self.btn_yes)
        lay.addLayout(row)

    # ---- execution --------------------------------------------------------
    def _start(self) -> None:
        from corpse.functions.training.environment_manager import PROJECT_ROOT
        from common.ambient.installer.sysinfo import detect_system
        self.btn_yes.setEnabled(False)
        self.btn_yes.hide()
        self.info.setText(tr("Download in progress: do not close this window.") if self.heavy else
                          tr("Installation in progress: do not close this window."))
        for w in (self.text, self.bar, self.btn_details):
            w.show()
        args = ["-m", "common.ambient.installer", "--os", detect_system().os_name, "--component", INSTALL_COMPONENT,
                "--yes", "--progress"] + (["--prefetch"] if self.heavy else [])
        self.proc = HiddenProcess(self)
        self.proc.line.connect(self._read)
        self.proc.done.connect(self._finished)
        self.proc.failed.connect(lambda _e: self._fail(tr("Could not start the installation.")))
        self.proc.start(_python(), args, PROJECT_ROOT)

    def _read(self, ln: str) -> None:
        if ln.startswith(PROGRESS_PREFIX):
            parts = ln.split(" ", 2)
            try:
                self.bar.setValue(int(float(parts[1])))
            except (IndexError, ValueError):
                pass
            if len(parts) > 2 and parts[2].strip():
                self.text.setText(parts[2].strip())
        elif ln.startswith(WARN_PREFIX):
            self.log.appendPlainText(tr("[WARNING] ") + ln[len(WARN_PREFIX):].strip())
        elif ln:
            self.log.appendPlainText(ln)

    def _finished(self, code: int) -> None:
        if code != 0:
            return self._fail(tr("The installation did not succeed. Check your connection and free space "
                                 "(see Details) and try again."))
        self.bar.setValue(100)
        self.ok = True
        self.accept()

    def _fail(self, msg: str) -> None:
        self.info.setText(f"<font color='#e57373'>{msg}</font>")
        self.btn_no.setText(tr("Close"))
        self.btn_details.setChecked(True)

    def _cancel(self) -> None:
        if self.proc and self.proc.running:
            if QMessageBox.question(self, tr("Cancel"), tr("Stop the installation? The partial download will be "
                                                          "resumed next time.")) != QMessageBox.StandardButton.Yes:
                return
            self.proc.kill()
        self.reject()

    def reject(self) -> None:
        if self.proc and self.proc.running:
            return self._cancel()
        super().reject()


def ensure_training_ready(parent: Optional[QWidget] = None) -> bool:
    """True if training can start now; False if cancelled, failed or the app is restarting."""
    from corpse.functions.training.environment_manager import get_cuda_status, launch_training_installer
    status = get_cuda_status()
    if not (status["install_needed"] or status["extras_pending"]):
        return True
    dlg = TrainingSetupDialog(status, parent)
    if not dlg.exec() or not dlg.ok:
        return False
    if dlg.heavy:
        if launch_training_installer():          # detached process: waits for the app to close, installs, reopens the app
            QApplication.quit()
        else:
            QMessageBox.critical(parent, tr("Error"), tr("Could not complete the activation. Restart the "
                                                         "application and try again from Training."))
        return False
    return True
