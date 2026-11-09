"""Catalog of what the server approved (photos or models): one tree, a folder per species in alphabetical order,
and inside it every photo / model with its data beside it. Filterable and sortable; photos open in a viewer."""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from common.i18n import tr, tr_error
from common.params import KIND_AREA, KINDS_VIDEO, VIDEO_SUFFIXES
from common.remote_tree import walk_remote
from common.ui.qt_utils import run_async, fit_columns

from corpse.functions.users.preview import IMAGE_SUFFIXES
from corpse.functions.users.session import Session
from .image_viewer import ImageViewerDialog
from .preview_dialog import PreviewDialog
from .transfer import TransferDialog

AREAS = KIND_AREA
COL_NAME, COL_COUNT, COL_SIZE, COL_UPLOADER, COL_APPROVER, COL_DATE, COL_FOLDER, COL_LABELS = range(8)
RECORD = Qt.ItemDataRole.UserRole                 # leaf data: the record; top-level data: the species
PLACEHOLDER = "__loading__"


def natural_key(text: str) -> List[Any]:
    """IMG_2 comes before IMG_10."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


class CatalogItem(QTreeWidgetItem):
    """A row that sorts by its meaning (size as a number, names in natural order); species stay alphabetical
    whatever the column and the direction."""

    def _sort_key(self, column: int) -> Any:
        rec = self.data(0, RECORD)
        if self.parent() is None:
            return natural_key(self.text(0))
        if column == COL_SIZE:
            return (rec or {}).get("size", 0)
        if column == COL_NAME:
            return (natural_key(self.text(0)), self.text(COL_DATE))
        return (self.text(column).lower(), natural_key(self.text(0)))

    def __lt__(self, other: "QTreeWidgetItem") -> bool:
        tree = self.treeWidget()
        column = tree.sortColumn() if tree is not None else 0
        if self.parent() is None:                                # species: always A→Z
            descending = tree is not None and tree.header().sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
            a, b = natural_key(self.text(0)), natural_key(other.text(0))
            return a > b if descending else a < b
        return self._sort_key(column) < other._sort_key(column)  # type: ignore[attr-defined]


class CatalogWidget(QWidget):
    """`kind` is "photos" or "model". Children of a species are loaded when it is opened."""

    def __init__(self, session: Session, kind: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session, self.kind, self.area = session, kind, AREAS[kind]
        self.items: List[Dict[str, Any]] = []
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("Filter..."))
        self.filter.setClearButtonEnabled(True)
        top.addWidget(self.filter, 1)
        lay.addLayout(top)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("Species"), tr("Videos") if kind in KINDS_VIDEO else tr("Photos"), tr("Size"),
                                   tr("Uploaded by"), tr("Approved by"), tr("Date"), tr("Folder"), tr("Labels")])
        fit_columns(self.tree)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setColumnHidden(COL_COUNT, kind == "model")
        self.tree.setColumnHidden(COL_FOLDER, kind == "model")
        self.tree.setColumnHidden(COL_LABELS, kind == "model")
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(COL_NAME, Qt.SortOrder.AscendingOrder)
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.btn_download = QPushButton(tr("Download"))
        self.btn_download.setEnabled(False)
        self.btn_collapse = QPushButton(tr("Collapse all"))
        row.addWidget(self.btn_download)
        row.addWidget(self.btn_collapse)
        row.addStretch(1)
        lay.addLayout(row)
        self.status = QLabel("")
        lay.addWidget(self.status)
        self.tree.itemSelectionChanged.connect(self._on_selection)
        self.tree.itemExpanded.connect(self._expanded)
        self.tree.itemDoubleClicked.connect(self._open)
        self.filter.textChanged.connect(self._apply_filter)
        self.btn_download.clicked.connect(self._download)
        self.btn_collapse.clicked.connect(self.tree.collapseAll)
        self.refresh()

    # ---- species ----------------------------------------------------------
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
        self.status.setText(tr("{n} species", n=self.tree.topLevelItemCount()))

    def _by_species(self) -> Dict[str, List[Dict[str, Any]]]:
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for i in self.items:
            groups.setdefault(i["species"], []).append(i)
        return groups

    def _fill(self, items: List[Dict[str, Any]]) -> None:
        self.items = items
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        for species, batches in sorted(self._by_species().items(), key=lambda kv: natural_key(kv[0])):
            top = CatalogItem([species, str(sum(int(b.get("items") or 0) for b in batches))])
            top.setData(0, RECORD, None)
            top.setData(0, Qt.ItemDataRole.UserRole + 1, {"species": species, "loaded": False})
            top.addChild(CatalogItem([tr("Loading...")]))         # lets the arrow appear: replaced when opened
            self.tree.addTopLevelItem(top)
        self.tree.setSortingEnabled(True)
        self._apply_filter()
        self._on_selection()

    def _state(self, top: QTreeWidgetItem) -> Dict[str, Any]:
        return top.data(0, Qt.ItemDataRole.UserRole + 1)

    # ---- the items of one species ----------------------------------------
    def _records(self, species: str) -> List[Dict[str, Any]]:
        """Every photo (or model file) of a species with the data shown beside it. Runs outside the GUI thread."""
        client, area = self.session.client, self.area
        batches = self._by_species().get(species, [])
        out: List[Dict[str, Any]] = []
        if self.kind == "model":
            folders = {str(PurePosixPath(b["path"]).parent) for b in batches}
            sizes = {f"{f}/{e['name']}": e.get("size", 0) for f in folders for e in client.list(area, f)
                     if e["type"] != "dir"}
            for b in batches:
                name = PurePosixPath(b["path"]).name
                out.append({"name": name, "rel": b["path"], "size": sizes.get(b["path"], 0), "batch": b, "folder": ""})
            return out
        wanted = VIDEO_SUFFIXES if self.kind in KINDS_VIDEO else IMAGE_SUFFIXES
        for b in sorted(batches, key=lambda b: (b["date"], b["path"])):
            base = PurePosixPath(b["path"])
            files = walk_remote(client, area, b["path"])
            labels = {rel for rel, _size in files if PurePosixPath(rel).suffix.lower() == ".txt"}
            for rel, size in files:
                if PurePosixPath(rel).suffix.lower() in wanted:
                    label = str(PurePosixPath(rel).with_suffix(".txt"))
                    out.append({"name": str(PurePosixPath(rel).relative_to(base)), "rel": rel, "size": size,
                                "batch": b, "folder": base.name, "label": label if label in labels else None})
        return out

    def _expanded(self, top: QTreeWidgetItem) -> None:
        if top.parent() is not None or self._state(top)["loaded"]:
            return
        state = self._state(top)
        state["loaded"] = True                                   # one request at a time per species
        run_async(self, lambda: self._records(state["species"]), lambda recs: self._add_children(top, recs),
                  lambda e: self._children_failed(top, e))

    def _children_failed(self, top: QTreeWidgetItem, e: Exception) -> None:
        self._state(top)["loaded"] = False
        self.status.setText(tr("Error: {msg}", msg=tr_error(e)))

    def _add_children(self, top: QTreeWidgetItem, records: List[Dict[str, Any]]) -> None:
        if self.tree.indexOfTopLevelItem(top) < 0:               # the list was refreshed meanwhile
            return
        self.tree.setSortingEnabled(False)
        top.takeChildren()
        for r in records:
            b = r["batch"]
            leaf = CatalogItem([r["name"], "", human_size(r["size"]), b["uploader"], b["approved_by"], b["date"],
                                r["folder"], tr("Yes") if r.get("label") else ""])
            leaf.setData(0, RECORD, r)
            top.addChild(leaf)
        self.tree.setSortingEnabled(True)
        self._apply_filter()

    # ---- filter -----------------------------------------------------------
    def _apply_filter(self, *_args) -> None:
        text = self.filter.text().strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            species = top.text(0).lower()
            if not text:
                top.setHidden(False)
                for k in range(top.childCount()):
                    top.child(k).setHidden(False)
                continue
            name_hit = text in species
            batch_hit = any(text in " ".join((b["uploader"], b["approved_by"], b["date"], b["path"])).lower()
                            for b in self._by_species().get(top.text(0), []))
            any_leaf = False
            for k in range(top.childCount()):
                leaf = top.child(k)
                rec = leaf.data(0, RECORD)
                hit = rec is not None and text in " ".join(leaf.text(c) for c in range(self.tree.columnCount())).lower()
                leaf.setHidden(not (name_hit or hit) and rec is not None)
                any_leaf = any_leaf or hit
            top.setHidden(not (name_hit or batch_hit or any_leaf))

    # ---- selection and viewer ----------------------------------------------
    def _selected(self) -> List[QTreeWidgetItem]:
        return [i for i in self.tree.selectedItems() if not i.isHidden()]

    def _on_selection(self) -> None:
        self.btn_download.setEnabled(bool(self._selected()))

    def _open(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        rec = item.data(0, RECORD)
        if rec is None or not self.session.online:
            return
        if self.kind in KINDS_VIDEO:
            self.status.setText(tr("Download the video to watch it."))
        elif self.kind != "model":
            ImageViewerDialog(self.session.client, self.area, rec["rel"], self, labels_area="datasets",
                              editable=self.session.is_admin and self.kind in ("photos", "stereo")).exec()
        else:
            PreviewDialog(self.session.client, "model", {"path": rec["rel"]}, self).exec()

    # ---- download ---------------------------------------------------------
    def _download(self) -> None:
        picked = self._selected()
        if not picked:
            return
        start = self.session.local_folders().get(self.area) or str(Path.home())
        dest = QFileDialog.getExistingDirectory(self, tr("Choose where to save"), start)
        if not dest:
            return
        wanted = [(i.parent() is None, i.text(0), i.data(0, RECORD)) for i in picked]
        client, area, kind = self.session.client, self.area, self.kind

        def plan() -> List[Any]:
            """(remote path, size, local path) for each file, without repeating one chosen twice."""
            files: Dict[str, Any] = {}
            for is_species, species, rec in wanted:
                recs = self._records(species) if is_species else [rec]
                for r in recs:
                    sp = PurePosixPath(r["rel"]).parts[0]
                    if kind == "model":                          # the model and its .json
                        base = PurePosixPath(r["rel"])
                        for rel, size in walk_remote(client, area, str(base.parent)):
                            p = PurePosixPath(rel)
                            if p.stem == base.stem and p.suffix in (".pt", ".json"):
                                files[rel] = (rel, size, Path(dest) / sp / p.name)
                    else:
                        files[r["rel"]] = (r["rel"], r["size"], Path(dest) / sp / r["folder"] / r["name"])
                        if r.get("label"):                       # the labels come with the media
                            lab = r["label"]
                            files[lab] = (lab, 0, Path(dest) / sp / r["folder"] / PurePosixPath(r["name"]).with_suffix(".txt"))
            return list(files.values())

        def fetch(rel: str, local: Path, cb: Any, cancel: Any) -> None:
            if not local.exists():                               # an interrupted download resumes from where it was
                client.download(area, rel, local, cb, cancel)

        def go(files: List[Any]) -> None:
            jobs = [(rel, size, lambda cb, cancel, r=rel, l=local: fetch(r, l, cb, cancel))
                    for rel, size, local in files]
            dlg = TransferDialog(tr("Download"), jobs, self)
            dlg.exec()
            ok = len(jobs) - len(dlg.errors)
            self.status.setText(tr("{n} files downloaded.", n=ok))
            if dlg.errors:
                QMessageBox.warning(self, tr("Transfer"), tr("Errors:") + "\n" + "\n".join(dlg.errors[:8]))

        run_async(self, plan, go, lambda e: self.status.setText(tr("Error: {msg}", msg=tr_error(e))))
