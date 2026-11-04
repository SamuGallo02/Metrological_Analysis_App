"""Catalogo di ciò che il server ha approvato (foto o modelli): per specie, con chi l'ha caricato e chi l'ha approvato."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from common.i18n import tr, tr_error
from common.params import AREA_SPECIES
from common.remote_tree import walk_remote
from common.ui.qt_utils import run_async, fit_columns

from corpse.functions.users.session import Session
from .transfer import TransferDialog

AREAS = {"photos": AREA_SPECIES, "model": "models"}


class CatalogWidget(QWidget):
    """Un albero specie → voci. `kind` è "photos" (una voce per invio approvato) o "model" (una per modello)."""

    def __init__(self, session: Session, kind: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session, self.kind, self.area = session, kind, AREAS[kind]
        self.items: List[Dict[str, Any]] = []
        lay = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("Species"), tr("Photos"), tr("Uploaded by"), tr("Approved by"), tr("Date")])
        fit_columns(self.tree)       
        self.tree.setColumnHidden(1, kind == "model")            # a model is a single file: no count
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.btn_download = QPushButton(tr("Download"))
        self.btn_download.setEnabled(False)
        self.btn_refresh = QPushButton(tr("Refresh"))
        row.addWidget(self.btn_download)
        row.addWidget(self.btn_refresh)
        row.addStretch(1)
        lay.addLayout(row)
        self.status = QLabel("")
        lay.addWidget(self.status)
        self.tree.currentItemChanged.connect(self._on_selection)
        self.btn_download.clicked.connect(self._download)
        self.btn_refresh.clicked.connect(self.refresh)
        self.refresh()

    # ---- elenco -----------------------------------------------------------
    def refresh(self) -> None:
        if not self.session.online:
            self._fill([])
            self.status.setText(tr("Offline."))
            return
        self.status.setText(tr("Loading..."))
        run_async(self, lambda: self.session.client.catalog(self.kind), self._loaded,
                  lambda e: self.status.setText(tr("Error: {msg}", msg=tr_error(e))))

    def _loaded(self, items: List[Dict[str, Any]]) -> None:
        self._fill(items)
        self.status.setText(tr("{n} items", n=len(items)))

    def _fill(self, items: List[Dict[str, Any]]) -> None:
        self.items = items
        self.tree.clear()
        groups: Dict[str, QTreeWidgetItem] = {}
        for i in items:                                          # il server li dà già in ordine di specie e data
            top = groups.get(i["species"])
            if top is None:
                top = QTreeWidgetItem([i["species"]])
                groups[i["species"]] = top
                self.tree.addTopLevelItem(top)
            child = QTreeWidgetItem([PurePosixPath(i["path"]).name, str(i["items"]), i["uploader"],
                                     i["approved_by"], i["date"]])
            child.setData(0, Qt.ItemDataRole.UserRole, i)
            top.addChild(child)
        self.tree.expandAll()
        self._on_selection()

    def _selected(self) -> Optional[Dict[str, Any]]:
        item = self.tree.currentItem()                           # una riga di specie non ha dati: non si scarica
        return None if item is None else item.data(0, Qt.ItemDataRole.UserRole)

    def _on_selection(self, *_args) -> None:
        self.btn_download.setEnabled(self._selected() is not None)

    # ---- scaricamento -----------------------------------------------------
    def _download(self) -> None:
        item = self._selected()
        if item is None:
            return
        start = self.session.local_folders().get(self.area) or str(Path.home())
        dest = QFileDialog.getExistingDirectory(self, tr("Choose where to save"), start)
        if not dest:
            return
        client, area, base = self.session.client, self.area, PurePosixPath(item["path"])

        def plan() -> List[Any]:
            if self.kind == "model":                             # il modello e il suo .json
                return [f for f in walk_remote(client, area, str(base.parent))
                        if PurePosixPath(f[0]).stem == base.stem and PurePosixPath(f[0]).suffix in (".pt", ".json")]
            return walk_remote(client, area, str(base))

        def local_of(rel: str) -> Path:
            if self.kind == "model":
                return Path(dest) / PurePosixPath(rel).name
            return Path(dest) / base.name / PurePosixPath(rel).relative_to(base)

        def fetch(rel: str, cb: Any, cancel: Any) -> None:
            local = local_of(rel)
            if not local.exists():                               # un download interrotto riprende da dove era
                client.download(area, rel, local, cb, cancel)

        def go(files: List[Any]) -> None:
            jobs = [(rel, size, lambda cb, cancel, r=rel: fetch(r, cb, cancel)) for rel, size in files]
            dlg = TransferDialog(tr("Download"), jobs, self)
            dlg.exec()
            ok = len(jobs) - len(dlg.errors)
            self.status.setText(tr("{n} files downloaded.", n=ok))
            if dlg.errors:
                QMessageBox.warning(self, tr("Transfer"), tr("Errors:") + "\n" + "\n".join(dlg.errors[:8]))

        run_async(self, plan, go, lambda e: self.status.setText(tr("Error: {msg}", msg=tr_error(e))))