"""Finestra di trasferimento con barra di avanzamento e Annulla."""
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from common.i18n import tr, tr_error
from common.qt_utils import Worker

from ..api import ApiError, Cancelled


class TransferDialog(QDialog):
    """Esegue una lista di trasferimenti. jobs: [(etichetta, byte, fn(progress_cb, cancel_cb))].
    Al termine: `errors` (testi) e `skipped` (gia' presenti sul server, HTTP 409)."""

    progress = Signal(int, int, str)       # byte fatti, byte totali, testo

    def __init__(self, title: str, jobs: List[Tuple[str, int, Callable]], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self.jobs, self.cancelled, self.errors, self.skipped = jobs, False, [], []
        lay = QVBoxLayout(self)
        self.label = QLabel("...")
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        lay.addWidget(self.label)
        lay.addWidget(self.bar)
        self.btn = QPushButton(tr("Cancel"))
        self.btn.clicked.connect(self._cancel)
        lay.addWidget(self.btn, alignment=Qt.AlignmentFlag.AlignRight)
        self.progress.connect(self._on_progress)
        self.total = max(1, sum(j[1] for j in jobs))
        self._thread = Worker(self._run, self)
        self._thread.finished.connect(self.accept)
        self._thread.start()

    def _cancel(self) -> None:
        self.cancelled = True
        self.btn.setEnabled(False)
        self.label.setText(tr("Cancelling..."))

    def _on_progress(self, done: int, total: int, text: str) -> None:
        self.bar.setValue(int(1000 * done / max(1, total)))
        self.label.setText(text)

    def _run(self) -> None:
        base = 0
        for i, (name, size, fn) in enumerate(self.jobs, 1):
            if self.cancelled:
                break
            text = f"({i}/{len(self.jobs)}) {name}"

            def cb(done: int, _t: int, base=base, text=text) -> None:
                self.progress.emit(base + done, self.total, text)

            try:
                fn(cb, lambda: self.cancelled)
            except Cancelled:
                break
            except ApiError as e:
                (self.skipped if e.status == 409 else self.errors).append(f"{name}: {tr_error(e)}")
            except OSError as e:
                self.errors.append(f"{name}: {e}")
            base += size
            self.progress.emit(base, self.total, text)

    def reject(self) -> None:
        self._cancel()
