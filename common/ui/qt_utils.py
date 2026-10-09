"""Small shared Qt tools: running functions outside the GUI thread."""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, List, Optional, Union

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QMessageBox, QWidget

from ..i18n import tr
from ..params import NO_WINDOW


class Worker(QThread):
    """Runs a function outside the GUI thread. done(result) or failed(exception)."""
    done = Signal(object)
    failed = Signal(object)

    def __init__(self, fn: Callable[[], Any], parent: Optional[QObject] = None):
        super().__init__(parent)
        self.fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self.fn())
        except Exception as e:                       # noqa: BLE001 - reported to the GUI
            self.failed.emit(e)


def run_async(owner: QObject, fn: Callable[[], Any], on_done: Callable[[Any], None],
              on_fail: Optional[Callable[[Exception], None]] = None) -> Worker:
    w = Worker(fn, owner)
    holders = getattr(owner, "_workers", None)
    if holders is None:
        holders = owner._workers = []
    holders.append(w)
    w.done.connect(on_done)
    w.failed.connect(on_fail or (lambda e: QMessageBox.warning(owner if isinstance(owner, QWidget) else None,
                                                                tr("Error"), str(e))))
    w.finished.connect(lambda: holders.remove(w) if w in holders else None)
    w.start()
    return w


class HiddenProcess(QObject):
    """Runs a program without any console window and reports its output line by line.

    Signals: line(str) for every output line, done(int) with the exit code, failed(str) if it cannot start.
    (QProcess cannot hide the console of a console program on Windows; subprocess with CREATE_NO_WINDOW can.)"""
    line = Signal(str)
    done = Signal(int)
    failed = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._proc: Optional[subprocess.Popen] = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, program: str, args: List[str], cwd: Union[str, Path]) -> None:
        try:
            self._proc = subprocess.Popen([program, *args], cwd=str(cwd), stdin=subprocess.DEVNULL,
                                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                          encoding="utf-8", errors="replace", **NO_WINDOW)
        except OSError as e:
            self.failed.emit(str(e))
            return
        threading.Thread(target=self._pump, args=(self._proc,), daemon=True).start()

    def _pump(self, proc: subprocess.Popen) -> None:
        for ln in proc.stdout:                         # signals are queued to the GUI thread
            self.line.emit(ln.rstrip("\r\n"))
        self.done.emit(proc.wait())

    def kill(self) -> None:
        if self.running:
            self._proc.kill()
