"""Finestra per scaricare un dataset di training dal server."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from common.i18n import tr, tr_error
from common.remote_tree import download_tree
from common.ui.qt_utils import run_async, fit_columns
from corpse.functions.training.server_data import DATASETS_AREA, group_datasets_by_species


class ServerDatasetDialog(QDialog):
    """Elenca i dataset del server e scarica quello scelto in `dest_dir/<nome>`.
    `client` è l'ApiClient della sessione (questa sezione non importa gli utenti)."""

    downloaded = Signal(str)             # nome del dataset scaricato
    progress = Signal(int, int)          # byte fatti, byte totali

    def __init__(self, client: Any, dest_dir: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.client, self.dest_dir = client, Path(dest_dir)
        self.cancelled, self._busy = False, False
        self.setWindowTitle(tr("Download a dataset from the server"))
        self.setMinimumWidth(820)

        lay = QVBoxLayout(self)
        self.status = QLabel(tr("Loading..."))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("Species / Dataset"), tr("Images"), tr("Uploaded by"), tr("Approved by"), tr("Date")])
        fit_columns(self.tree)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setVisible(False)
        lay.addWidget(self.status)
        lay.addWidget(self.tree, 1)
        lay.addWidget(self.bar)

        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_download = QPushButton(tr("Download"))
        self.btn_download.setEnabled(False)
        self.btn_cancel = QPushButton(tr("Cancel"))
        row.addWidget(self.btn_download)
        row.addWidget(self.btn_cancel)
        lay.addLayout(row)

        self.tree.currentItemChanged.connect(self._on_selection)
        self.btn_download.clicked.connect(self._start)
        self.btn_cancel.clicked.connect(self.reject)
        self.progress.connect(self._on_progress)
        run_async(self, lambda: self.client.catalog("dataset"), self._fill, self._failed)

    # ---- elenco ---------------------------------------------------------
    def _fill(self, items: List[dict]) -> None:
        self.tree.clear()
        for species, members in group_datasets_by_species(items):
            top = QTreeWidgetItem([species or tr("No species declared")])
            for i in members:
                child = QTreeWidgetItem([PurePosixPath(i["path"]).name, str(i["items"]), i["uploader"], i["approved_by"], i["date"]])
                child.setData(0, Qt.ItemDataRole.UserRole, i["path"])          # the name of the folder on the server
                top.addChild(child)
            self.tree.addTopLevelItem(top)
        self.tree.expandAll()
        self.status.setText("" if items else tr("No datasets on the server."))

    def _selected_name(self) -> Optional[str]:
        item = self.tree.currentItem()                       # a species row has no name: it is not downloadable
        return None if item is None else item.data(0, Qt.ItemDataRole.UserRole)

    def _on_selection(self, *_args) -> None:
        self.btn_download.setEnabled(self._selected_name() is not None and not self._busy)

    # ---- scaricamento -----------------------------------------------------
    def _start(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        self._busy = True
        self.btn_download.setEnabled(False)
        self.tree.setEnabled(False)
        self.bar.setVisible(True)
        self.status.setText(tr("Downloading {name}...", name=name))

        def job() -> str:
            flat = PurePosixPath(name).name                   # in the server the dataset is inside a species folder
            download_tree(self.client, DATASETS_AREA, name, self.dest_dir / flat,
                          progress=lambda done, total: self.progress.emit(done, total),
                          cancel=lambda: self.cancelled)
            return flat

        run_async(self, job, self._finished, self._failed)

    def _on_progress(self, done: int, total: int) -> None:
        self.bar.setValue(int(1000 * done / max(1, total)))

    def _finished(self, name: str) -> None:
        self._busy = False
        self.downloaded.emit(name)
        self.accept()

    def _failed(self, e: Exception) -> None:
        self._busy = False
        if self.cancelled:                                 # l'annullamento arriva come errore dal client
            return super().reject()
        self.tree.setEnabled(True)
        self.bar.setVisible(False)
        self.status.setText(tr("Error: {msg}", msg=tr_error(e)))
        self._on_selection()

    def reject(self) -> None:
        if self._busy:                                     # a metà scaricamento: si ferma, poi la finestra si chiude
            self.cancelled = True
            self.status.setText(tr("Cancelling..."))
            return
        super().reject()