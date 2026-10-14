"""Explorer-like view of the server folders: one tree, folders open on demand (lazy loading)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton, QStyle, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from common.format import fmt_size, fmt_time
from common.i18n import tr, tr_error
from common.params import AREAS_SHARED
from common.ui.qt_utils import run_async

from corpse.functions.users.session import Session
from .labels import area_label

ROLE = Qt.ItemDataRole.UserRole
LOADED = "loaded"


class ServerTreeDialog(QDialog):
    """Tree of the server areas. Opening a folder (arrow or double click) lists its content, nested folders
    included; each level is requested from the server only when it is opened."""

    folder_chosen = Signal(str, str)                  # area, path: the caller shows that folder in its list

    def __init__(self, session: Session, areas: Sequence[str] = AREAS_SHARED, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        self.areas = tuple(areas)
        self.setWindowTitle(tr("Folder tree"))
        self.resize(780, 560)
        st = self.style()
        self._dir_icon = st.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        self._file_icon = st.standardIcon(QStyle.StandardPixmap.SP_FileIcon)

        lay = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("Name"), tr("Size"), tr("Modified")])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.itemExpanded.connect(self._expanded)
        self.tree.itemDoubleClicked.connect(self._double_click)
        lay.addWidget(self.tree, 1)

        row = QHBoxLayout()
        self.btn_refresh = QPushButton(tr("Refresh"))
        self.btn_refresh.clicked.connect(self.reload)
        self.btn_collapse = QPushButton(tr("Collapse all"))
        self.btn_collapse.clicked.connect(self.tree.collapseAll)
        self.btn_open = QPushButton(tr("Show in the list"))
        self.btn_open.clicked.connect(self._choose)
        for b in (self.btn_refresh, self.btn_collapse):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self.btn_open)
        lay.addLayout(row)
        self.status = QLabel("")
        lay.addWidget(self.status)
        self.reload()

    # ---- building the tree ------------------------------------------------
    def reload(self) -> None:
        self.tree.clear()
        if not self.session.online:
            self.status.setText(tr("Offline."))
            return
        self.status.setText("")
        for a in self.areas:
            it = QTreeWidgetItem([area_label(a), "", ""])
            it.setIcon(0, self._dir_icon)
            it.setData(0, ROLE, {"area": a, "path": "", "type": "dir", LOADED: False})
            it.addChild(QTreeWidgetItem([tr("Loading..."), "", ""]))            # placeholder: shows the arrow
            self.tree.addTopLevelItem(it)

    def _expanded(self, item: QTreeWidgetItem) -> None:
        info = item.data(0, ROLE)
        if not info or info.get(LOADED):
            return
        info[LOADED] = True                                                     # avoids a second request
        item.setData(0, ROLE, info)
        area, path = info["area"], info["path"]

        def done(entries: List[Dict[str, Any]]) -> None:
            item.takeChildren()
            if not entries:
                item.addChild(QTreeWidgetItem([tr("(empty)"), "", ""]))
            # folders first, like the Windows file explorer
            for e in sorted(entries, key=lambda e: (e["type"] != "dir", e["name"].lower())):
                is_dir = e["type"] == "dir"
                child_path = f"{path}/{e['name']}" if path else e["name"]
                ch = QTreeWidgetItem([e["name"], "" if is_dir else fmt_size(e["size"]), fmt_time(e["mtime"])])
                ch.setIcon(0, self._dir_icon if is_dir else self._file_icon)
                ch.setData(0, ROLE, {"area": area, "path": child_path, "type": e["type"], LOADED: False})
                if is_dir:
                    ch.addChild(QTreeWidgetItem([tr("Loading..."), "", ""]))
                item.addChild(ch)
            self.status.setText(tr("{n} items", n=len(entries)))

        def fail(e: Exception) -> None:
            info[LOADED] = False                                                # it can be retried
            item.takeChildren()
            item.addChild(QTreeWidgetItem([tr("Error: {msg}", msg=tr_error(e)), "", ""]))

        run_async(self, lambda: self.session.client.list(area, path), done, fail)

    # ---- actions ---------------------------------------------------------
    def _double_click(self, item: QTreeWidgetItem, _col: int) -> None:
        info = item.data(0, ROLE)
        if info and info["type"] == "dir":
            item.setExpanded(not item.isExpanded())

    def _choose(self) -> None:
        item = self.tree.currentItem()
        info = item.data(0, ROLE) if item else None
        if not info:
            self.status.setText(tr("Select a folder."))
            return
        path = info["path"]
        if info["type"] != "dir":                                               # a file: its folder
            path = path.rsplit("/", 1)[0] if "/" in path else ""
        self.folder_chosen.emit(info["area"], path)
        self.accept()
