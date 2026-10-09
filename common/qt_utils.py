"""Piccoli strumenti Qt condivisi: esecuzione di funzioni fuori dal thread grafico."""
from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QMessageBox, QWidget

from .i18n import tr


class Worker(QThread):
    """Esegue una funzione fuori dal thread grafico. done(risultato) o failed(eccezione)."""
    done = Signal(object)
    failed = Signal(object)

    def __init__(self, fn: Callable[[], Any], parent: Optional[QObject] = None):
        super().__init__(parent)
        self.fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self.fn())
        except Exception as e:                       # noqa: BLE001 - riportata alla GUI
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
