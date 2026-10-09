"""Pulsante "Train": avvisa che servono delle estensioni e, se l'utente accetta, le installa da sole
mostrando una barra di avanzamento.

    from training.setup_dialog import ensure_training_ready
    if ensure_training_ready(self):      # True = si puo' procedere subito con il training
        ...apri la pagina di training...

Due casi, decisi da core.environment_manager.get_cuda_status():
  * solo extra leggeri (pochi MB): installazione completa nella finestra, poi si prosegue.
  * PyTorch con supporto GPU (alcuni GB): la finestra SCARICA tutto con la barra (l'app resta aperta);
    poi l'app si riavvia da sola per sostituire PyTorch (con l'app aperta i file sono bloccati) e il
    processo di installazione, staccato, termina in pochi istanti grazie ai file gia' scaricati.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)

from common.i18n import tr

from .params import INSTALL_COMPONENT, KILL_WAIT_MS, PROGRESS_PREFIX, WARN_PREFIX


def _python() -> str:
    from installer import state                       # moduli dell'installatore dell'app (import tardivo)
    from installer.sysinfo import detect_system
    py = state.venv_python(detect_system().os_name)
    return str(py if Path(py).exists() else sys.executable)


class TrainingSetupDialog(QDialog):
    """Fase 1: avviso e conferma. Fase 2: barra di avanzamento."""

    def __init__(self, status: dict, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Components for training"))
        self.setMinimumWidth(480)
        self.heavy = bool(status["install_needed"])
        self.proc: Optional[QProcess] = None
        self.ok = False
        self._buf = ""

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

    # ---- esecuzione --------------------------------------------------------
    def _start(self) -> None:
        from core.environment_manager import PROJECT_ROOT
        from installer.sysinfo import detect_system
        self.btn_yes.setEnabled(False)
        self.btn_yes.hide()
        self.info.setText(tr("Download in progress: do not close this window.") if self.heavy else
                          tr("Installation in progress: do not close this window."))
        for w in (self.text, self.bar, self.btn_details):
            w.show()
        args = ["-m", "installer", "--os", detect_system().os_name, "--component", INSTALL_COMPONENT,
                "--yes", "--progress"] + (["--prefetch"] if self.heavy else [])
        self.proc = QProcess(self)
        self.proc.setWorkingDirectory(str(PROJECT_ROOT))
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(lambda _e: self._fail(tr("Could not start the installation.")))
        self.proc.start(_python(), args)

    def _read(self) -> None:
        self._buf += bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        *lines, self._buf = self._buf.split("\n")
        for ln in lines:
            ln = ln.rstrip("\r")
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

    def _finished(self, code: int, _status) -> None:
        self._read()
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
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            if QMessageBox.question(self, tr("Cancel"), tr("Stop the installation? The partial download will be "
                                                          "resumed next time.")) != QMessageBox.StandardButton.Yes:
                return
            self.proc.kill()
            self.proc.waitForFinished(KILL_WAIT_MS)
        self.reject()

    def reject(self) -> None:
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            return self._cancel()
        super().reject()


def ensure_training_ready(parent: Optional[QWidget] = None) -> bool:
    """True se il training puo' partire adesso; False se annullato, fallito o se l'app si sta riavviando."""
    from core.environment_manager import get_cuda_status, launch_training_installer
    status = get_cuda_status()
    if not (status["install_needed"] or status["extras_pending"]):
        return True
    dlg = TrainingSetupDialog(status, parent)
    if not dlg.exec() or not dlg.ok:
        return False
    if dlg.heavy:
        if launch_training_installer():          # processo staccato: attende la chiusura, installa, riapre l'app
            QApplication.quit()
        else:
            QMessageBox.critical(parent, tr("Error"), tr("Could not complete the activation. Restart the "
                                                         "application and try again from Training."))
        return False
    return True
