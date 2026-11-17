"""Training asked of the server: the request, and the list of what was asked with how it is going.

The server only holds the queue; a computer with a graphics card (the worker) does the work. So the user can ask
for a training and close the application.

Autore: Samuele Gallo
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from common.format import fmt_time
from common.i18n import tr, tr_error
from common.params import JOB_OPEN, JOB_QUEUED
from common.ui.qt_utils import run_async
from common.ui.server_state import server_note, server_ready

from corpse.functions.training.config import BASE_MODEL_OPTIONS, DEFAULT_BATCH, DEFAULT_EPOCHS, DEFAULT_IMGSZ
from corpse.functions.training.server_data import list_server_datasets

def status_label(status: str) -> str:
    """The state of a request, in the user's language."""
    return {"queued": tr("Waiting"), "running": tr("Training"), "done": tr("Done"), "failed": tr("Failed"),
            "cancelled": tr("Cancelled")}.get(status, status)


class RequestTrainingDialog(QDialog):
    """What to train and with which settings."""

    def __init__(self, client: Any, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.client = client
        self.setWindowTitle(tr("Ask the server for a training"))
        lay = QVBoxLayout(self)
        hint = QLabel(tr("The server puts the request in a queue: a computer with a graphics card trains the model "
                         "and publishes it. You can close the application in the meantime."))
        hint.setWordWrap(True)
        lay.addWidget(hint)
        form = QFormLayout()
        self.dataset = QComboBox()
        self.base = QComboBox()
        self.base.addItems(BASE_MODEL_OPTIONS)
        self.epochs = QSpinBox()
        self.epochs.setRange(1, 1000)
        self.epochs.setValue(DEFAULT_EPOCHS)
        self.imgsz = QSpinBox()
        self.imgsz.setRange(64, 2048)
        self.imgsz.setSingleStep(32)
        self.imgsz.setValue(DEFAULT_IMGSZ)
        self.batch = QSpinBox()
        self.batch.setRange(1, 128)
        self.batch.setValue(DEFAULT_BATCH)
        self.species = QLineEdit()
        self.species.setPlaceholderText("Pinna nobilis")
        form.addRow(tr("Dataset of the server:"), self.dataset)
        form.addRow(tr("Base model:"), self.base)
        form.addRow(tr("Epochs:"), self.epochs)
        form.addRow(tr("Image size:"), self.imgsz)
        form.addRow(tr("Batch:"), self.batch)
        form.addRow(tr("Species (to publish it):"), self.species)
        lay.addLayout(form)
        self.status = QLabel(tr("Loading..."))
        lay.addWidget(self.status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        lay.addWidget(self.buttons)
        run_async(self, lambda: list_server_datasets(client), self._fill,
                  lambda e: self.status.setText(tr("Error: {msg}", msg=tr_error(e))))

    def _fill(self, datasets: List[Dict[str, Any]]) -> None:
        usable = [d["name"] for d in datasets if d.get("valid")]
        self.dataset.addItems(usable)
        self.status.setText(tr("{n} datasets", n=len(usable)) if usable
                            else tr("The server has no dataset ready for training."))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(usable))

    def request(self) -> Dict[str, Any]:
        return self.client.request_training(self.dataset.currentText(), self.base.currentText(),
                                            self.epochs.value(), self.imgsz.value(), self.batch.value(),
                                            self.species.text().strip())


class ServerTrainingWidget(QWidget):
    """The requests made to the server: state, worker and result."""

    def __init__(self, session: Any, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        self.jobs: List[Dict[str, Any]] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.btn_request = QPushButton(tr("Ask the server for a training..."))
        self.btn_request.clicked.connect(self._request)
        self.btn_cancel = QPushButton(tr("Cancel the request"))
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_refresh = QPushButton(tr("Refresh"))
        self.btn_refresh.clicked.connect(self.refresh)
        for b in (self.btn_request, self.btn_cancel, self.btn_refresh):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([tr("Dataset"), tr("Species"), tr("State"), tr("Asked on"),
                                              tr("Where"), tr("Detail")])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table, 1)
        self.status = QLabel("")
        lay.addWidget(self.status)
        self.refresh()

    # ---- data ---------------------------------------------------------
    def _online(self) -> bool:
        return bool(self.session and server_ready(self.session))

    def refresh(self) -> None:
        for b in (self.btn_request, self.btn_cancel):
            b.setEnabled(self._online())
        if not self._online():
            self.status.setText(tr("You are offline: the server folders are not available."))
            self.table.setRowCount(0)
            return
        self.status.setText(tr("Loading..."))
        everyone = bool(getattr(self.session, "is_admin", False))
        run_async(self, lambda: self.session.client.training_jobs(everyone=everyone), self._fill,
                  lambda e: self.status.setText(tr("Error: {msg}", msg=tr_error(e))))

    def _fill(self, jobs: List[Dict[str, Any]]) -> None:
        self.jobs = jobs
        self.table.setRowCount(len(jobs))
        for i, j in enumerate(jobs):
            values = [j["dataset"], j.get("species", ""), status_label(j["status"]), fmt_time(j["created"]),
                      j.get("worker", "") or j["username"], j.get("message", "")]
            for c, v in enumerate(values):
                self.table.setItem(i, c, QTableWidgetItem(str(v)))
        waiting = sum(1 for j in jobs if j["status"] in JOB_OPEN)
        self.status.setText(tr("{n} requests, {waiting} still open", n=len(jobs), waiting=waiting))

    def _current(self) -> Optional[Dict[str, Any]]:
        r = self.table.currentRow()
        return self.jobs[r] if 0 <= r < len(self.jobs) else None

    # ---- actions ------------------------------------------------------
    def _request(self) -> None:
        dialog = RequestTrainingDialog(self.session.client, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        run_async(self, dialog.request, lambda _job: self.refresh(),
                  lambda e: QMessageBox.warning(self, tr("Training"), tr_error(e)))

    def _cancel(self) -> None:
        job = self._current()
        if job is None:
            return QMessageBox.information(self, tr("Training"), tr("Select a request."))
        if job["status"] != JOB_QUEUED:
            return QMessageBox.information(self, tr("Training"),
                                           tr("Only a training that is still waiting can be cancelled."))
        run_async(self, lambda: self.session.client.cancel_training(job["id"]), lambda _j: self.refresh(),
                  lambda e: QMessageBox.warning(self, tr("Training"), tr_error(e)))
