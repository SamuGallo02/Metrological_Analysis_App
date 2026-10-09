"""Startup repair of the virtual environment: question, progress window and restart (see installer/integrity.py)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional

from common.i18n import init_language, tr
from common.params import PROGRESS_PREFIX, WARN_PREFIX

from .installer import integrity, state
from .installer.sysinfo import detect_os


def _python(os_name: str) -> str:
    py = state.venv_python(os_name)
    return str(py if Path(py).exists() else sys.executable)


def repair_at_startup(project_root: Path, deep: bool = False) -> str:
    """Checks the environment and, if some package is damaged, asks and repairs it showing a progress bar.

    Returns "ok" (nothing to do, or repaired: go on), "skipped" (the user declined) or "quit" (the repair was
    handed to a background process that reopens the app: the caller must exit)."""
    damaged = integrity.startup_check(deep)
    if not damaged:
        return "ok"
    listing = "\n".join(f"- {d}" for d in list(damaged.values())[:6])
    os_name = detect_os()
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        QApplication.instance() or QApplication(sys.argv)
        init_language()
        yes = QMessageBox.question(None, tr("Damaged files"),
                                   tr("Some installed libraries are damaged:") + "\n\n" + listing + "\n\n"
                                   + tr("Repair them now? Only the damaged packages are downloaded again, "
                                        "then the app reopens by itself."),
                                   ) == QMessageBox.StandardButton.Yes
    except Exception:                                   # Qt cannot start: repair without asking, in the background
        print("[WARNING] Damaged libraries:\n" + listing + "\nRepairing...")
        return "quit" if integrity.launch_repair(project_root, os_name, deep) else "skipped"
    if not yes:
        return "skipped"
    if integrity.touches_qt(damaged):                   # Qt files are locked by this very process
        return "quit" if integrity.launch_repair(project_root, os_name, deep) else "skipped"
    return "ok" if _run_with_progress(project_root, os_name, deep) else "skipped"


def _run_with_progress(project_root: Path, os_name: str, deep: bool) -> bool:
    """Runs the repair in a windowless process, with a progress window. True if it succeeded."""
    from PySide6.QtWidgets import (QApplication, QDialog, QLabel, QMessageBox, QPlainTextEdit, QProgressBar,
                                   QPushButton, QVBoxLayout)

    from common.ui.qt_utils import HiddenProcess

    class _Dialog(QDialog):
        def reject(self) -> None:                       # Esc / close would leave the repair running unseen
            if not proc.running:
                super().reject()

    dlg = _Dialog()
    dlg.setWindowTitle(tr("Repairing files"))
    dlg.setMinimumWidth(520)
    lay = QVBoxLayout(dlg)
    text = QLabel(tr("Checking the files..."))
    bar = QProgressBar()
    bar.setRange(0, 100)
    log = QPlainTextEdit()
    log.setReadOnly(True)
    log.setMaximumBlockCount(500)
    log.setMinimumHeight(140)
    log.hide()
    details = QPushButton(tr("Details"))
    details.setCheckable(True)
    details.toggled.connect(log.setVisible)
    for w in (text, bar, details, log):
        lay.addWidget(w)
    result: Dict[str, Optional[bool]] = {"ok": None}

    proc = HiddenProcess(dlg)

    def on_line(ln: str) -> None:
        if ln.startswith(PROGRESS_PREFIX):
            parts = ln.split(" ", 2)
            try:
                bar.setValue(int(float(parts[1])))
            except (IndexError, ValueError):
                pass
            if len(parts) > 2 and parts[2].strip():
                text.setText(parts[2].strip())
        elif ln.startswith(WARN_PREFIX):
            log.appendPlainText(tr("[WARNING] ") + ln[len(WARN_PREFIX):].strip())
        elif ln:
            log.appendPlainText(ln)

    def on_done(code: int) -> None:
        result["ok"] = code == 0
        dlg.accept()

    def on_fail(_msg: str) -> None:
        result["ok"] = False
        dlg.accept()

    proc.line.connect(on_line)
    proc.done.connect(on_done)
    proc.failed.connect(on_fail)
    proc.start(_python(os_name), ["-m", "common.ambient.installer", "--os", os_name, "--repair", "--yes",
                                  "--progress"] + (["--deep"] if deep else []), project_root)
    dlg.exec()
    app = QApplication.instance()
    if app:
        app.processEvents()
    if not result["ok"]:
        QMessageBox.warning(None, tr("Repairing files"),
                            tr("The repair did not succeed. Check your connection and free space, then restart the application."))
    return bool(result["ok"])
