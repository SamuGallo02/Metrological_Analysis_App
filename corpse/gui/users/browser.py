"""Browse the server folders. Common areas: everyone reads and uploads, only the 'server' role edits or
deletes. Personal area ('mine'): the owner can do everything, within the quota."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QMessageBox, QProgressBar, QPushButton, QTabBar, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from common.format import fmt_size, fmt_time
from common.i18n import tr, tr_error
import re

from common.params import AREA_MINE, AREAS_SHARED, SPECIES_EXAMPLE, SPECIES_RE
from common.ui.qt_utils import run_async

from corpse.functions.users.session import Session
from .labels import area_label
from .transfer import TransferDialog


class ServerBrowserWidget(QWidget):
    def __init__(self, session: Session, areas: Sequence[str] = AREAS_SHARED, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        self.areas = tuple(areas)
        self.area, self.path = self.areas[0], ""
        lay = QVBoxLayout(self)

        self.tabs = QTabBar()
        for a in self.areas:
            self.tabs.addTab(area_label(a))
        self.tabs.currentChanged.connect(self._area_changed)
        self.tabs.setVisible(len(self.areas) > 1)
        lay.addWidget(self.tabs)

        self.note = QLabel()
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        self.quota = QProgressBar()                 # only for the personal area
        self.quota.setFormat("%v / %m MB")
        self.quota.hide()
        lay.addWidget(self.quota)
        self.crumb = QLabel()
        lay.addWidget(self.crumb)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("Name"), tr("Type"), tr("Size"), tr("Modified")])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setRootIsDecorated(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.itemDoubleClicked.connect(self._open)
        lay.addWidget(self.tree, 1)

        row = QHBoxLayout()
        self.btn_up = self._btn(tr("Up"), self._up, row)
        self.btn_refresh = self._btn(tr("Refresh"), self.refresh, row)
        self.btn_dl = self._btn(tr("Download"), self._download, row)
        self.btn_up_files = self._btn(tr("Upload files..."), self._upload_files, row)
        self.btn_up_dir = self._btn(tr("Upload folder..."), self._upload_dir, row)
        self.btn_mkdir = self._btn(tr("New folder"), self._mkdir, row)
        row.addStretch(1)
        self.btn_rename = self._btn(tr("Rename/Move"), self._rename, row)
        self.btn_approve = self._btn(tr("Approve model"), self._approve, row)
        self.btn_delete = self._btn(tr("Delete"), self._delete, row)
        lay.addLayout(row)
        self.status = QLabel("")
        lay.addWidget(self.status)
        self._apply_role()
        self.refresh()

    def _btn(self, text: str, slot: Callable, row: QHBoxLayout) -> QPushButton:
        b = QPushButton(text)
        b.clicked.connect(slot)
        row.addWidget(b)
        return b

    # ---- state -------------------------------------------------------------
    def _can_modify(self) -> bool:
        return (self.area == AREA_MINE and self.session.can("mine.manage")) or self.session.can("files.modify")

    def _apply_role(self) -> None:
        self.btn_rename.setVisible(self._can_modify())
        self.btn_delete.setVisible(self._can_modify())
        self.btn_approve.setVisible(self.session.can("models.approve") and self.area == "models")
        self.btn_mkdir.setEnabled(self.session.online)
        self._update_note()

    def _update_note(self) -> None:
        if not self.session.online:
            text = f"<i>{tr('You are offline: the server folders are not available.')}</i>"
        elif self.area == AREA_MINE:
            text = tr("Your personal folder on the server: only you can see it. You can add, "
                      "rename, move and delete.")
        elif self.session.is_admin:
            text = tr("As an administrator you can modify and delete.")
            if self.area == "models":
                text += " " + tr("Models in <b>_pending</b> are waiting for approval.")
        elif self.area == "models":
            text = tr("You can download approved models and upload new ones: an administrator checks them before "
                      "publishing. Models are grouped by the scientific name of the species (Genus species).")
        else:
            text = tr("You can read, download and add files; you cannot modify or delete existing ones.")
        self.note.setText(text)

    def _area_changed(self, i: int) -> None:
        self.area, self.path = self.areas[i], ""
        self._apply_role()
        self.refresh()

    def _selected(self) -> List[Dict[str, Any]]:
        return [it.data(0, Qt.ItemDataRole.UserRole) for it in self.tree.selectedItems()]

    def _rel(self, name: str) -> str:
        return f"{self.path}/{name}" if self.path else name

    def _refresh_quota(self) -> None:
        show = self.area == AREA_MINE and self.session.online
        self.quota.setVisible(show)
        if not show:
            return

        def done(u: Dict[str, int]) -> None:
            mb = max(1, u["quota"] >> 20)
            self.quota.setMaximum(mb)
            self.quota.setValue(min(mb, u["used"] >> 20))

        run_async(self, self.session.client.usage, done, lambda e: None)

    # ---- list ------------------------------------------------------------
    def refresh(self) -> None:
        self.crumb.setText(f"<b>{area_label(self.area)}</b> / {self.path.replace('/', ' / ')}")
        self.tree.clear()
        if not self.session.online:
            self.status.setText(tr("Offline."))
            return
        self.status.setText(tr("Loading..."))
        self._refresh_quota()
        area, path = self.area, self.path

        def done(entries: List[Dict[str, Any]]) -> None:
            if (area, path) != (self.area, self.path):
                return
            for e in entries:
                is_dir = e["type"] == "dir"
                it = QTreeWidgetItem([(tr("[folder] ") if is_dir else "") + e["name"],
                                      tr("Folder") if is_dir else tr("File"),
                                      "" if is_dir else fmt_size(e["size"]), fmt_time(e["mtime"])])
                it.setData(0, Qt.ItemDataRole.UserRole, e)
                self.tree.addTopLevelItem(it)
            self.status.setText(tr("{n} items", n=len(entries)))

        run_async(self, lambda: self.session.client.list(area, path), done,
                  lambda e: self.status.setText(tr("Error: {msg}", msg=tr_error(e))))

    def _open(self, item: QTreeWidgetItem) -> None:
        e = item.data(0, Qt.ItemDataRole.UserRole)
        if e["type"] == "dir":
            self.path = self._rel(e["name"])
            self.refresh()

    def _up(self) -> None:
        self.path = self.path.rsplit("/", 1)[0] if "/" in self.path else ""
        self.refresh()

    def _walk_remote(self, rel: str, out: List[Tuple[str, int]]) -> None:
        for e in self.session.client.list(self.area, rel):
            child = f"{rel}/{e['name']}"
            if e["type"] == "dir":
                self._walk_remote(child, out)
            else:
                out.append((child, e["size"]))

    def _start_dir(self) -> str:
        folders = self.session.local_folders()
        return folders.get(self.area) or str(Path.home())

    # ---- transfers -----------------------------------------------------
    def _download(self) -> None:
        sel = self._selected()
        if not sel:
            return QMessageBox.information(self, tr("Download"), tr("Select one or more files or folders."))
        start = self._start_dir()
        Path(start).mkdir(parents=True, exist_ok=True)
        dest = QFileDialog.getExistingDirectory(self, tr("Choose where to save"), start)
        if not dest:
            return
        dest_dir = Path(dest)
        self.status.setText(tr("Preparing the list..."))

        def plan() -> List[Tuple[str, int]]:
            items: List[Tuple[str, int]] = []
            for e in sel:
                rel = self._rel(e["name"])
                if e["type"] == "dir":
                    self._walk_remote(rel, items)
                else:
                    items.append((rel, e["size"]))
            return items

        def go(items: List[Tuple[str, int]]) -> None:
            base, jobs = self.path, []
            for rel, size in items:
                if self.area == "models":                      # keeps the species folder: models/<Genus species>/x.pt
                    local = dest_dir / Path(rel)
                else:
                    local = dest_dir / Path(rel[len(base):].lstrip("/") if base else rel)
                if local.exists():
                    continue
                jobs.append((rel, size, lambda cb, cancel, rel=rel, local=local:
                             self.session.client.download(self.area, rel, local, cb, cancel)))
            if not jobs:
                return self.status.setText(tr("Nothing to download (files already present)."))
            dlg = TransferDialog(tr("Download"), jobs, self)
            dlg.exec()
            self._report(dlg, downloaded=True)

        run_async(self, plan, go, lambda e: self.status.setText(tr("Error: {msg}", msg=tr_error(e))))

    def _with_species(self, pairs: List[Tuple[Path, str]]) -> Optional[List[Tuple[Path, str]]]:
        """Models are stored in a folder named after the scientific name: asks for it when it is not in the path."""
        if self.area != "models" or not pairs:
            return pairs
        if all(re.fullmatch(SPECIES_RE, r.split("/")[0]) for _l, r in pairs):
            return pairs
        species, ok = QInputDialog.getText(
            self, tr("Scientific name"),
            tr("Scientific name of the species (Genus species), for example {example}:", example=SPECIES_EXAMPLE))
        species = species.strip()
        if not ok or not re.fullmatch(SPECIES_RE, species):
            if ok:
                QMessageBox.warning(self, tr("Scientific name"),
                                    tr("Enter the scientific name as 'Genus species', for example {example}.",
                                       example=SPECIES_EXAMPLE))
            return None
        return [(l, f"{species}/{r}") for l, r in pairs]

    def _upload_paths(self, pairs: List[Tuple[Path, str]]) -> None:
        pairs = self._with_species(pairs)
        if not pairs:
            return
        jobs = [(remote, local.stat().st_size, lambda cb, cancel, l=local, r=remote:
                 self.session.client.upload(self.area, r, l, cb, cancel)) for local, remote in pairs]
        if not jobs:
            return
        dlg = TransferDialog(tr("Upload"), jobs, self)
        dlg.exec()
        self._report(dlg, downloaded=False)
        self.refresh()

    def _upload_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, tr("Choose the files to upload"), self._start_dir())
        self._upload_paths([(Path(f), self._rel(Path(f).name)) for f in files])

    def _upload_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Choose the folder to upload"), self._start_dir())
        if not d:
            return
        root = Path(d)
        self._upload_paths([(p, self._rel(f"{root.name}/{p.relative_to(root).as_posix()}"))
                            for p in sorted(root.rglob("*")) if p.is_file()])

    def _report(self, dlg: TransferDialog, downloaded: bool) -> None:
        n_ok = len(dlg.jobs) - len(dlg.errors) - len(dlg.skipped)
        first = tr("{n} files downloaded.", n=n_ok) if downloaded else tr("{n} files uploaded.", n=n_ok)
        text = first
        if dlg.skipped:
            text += "\n" + tr("Already on the server (not overwritten): {n}.", n=len(dlg.skipped))
        if dlg.errors:
            text += "\n\n" + tr("Errors:") + "\n" + "\n".join(dlg.errors[:8])
        pending = self.area == "models" and not self.session.is_admin and not downloaded and n_ok
        if pending:
            text += "\n\n" + tr("Uploaded models are waiting for approval by an administrator.")
        self.status.setText(first)
        if dlg.errors or dlg.skipped or pending:
            QMessageBox.information(self, tr("Transfer"), text)

    def _mkdir(self) -> None:
        name, ok = QInputDialog.getText(self, tr("New folder"), tr("Folder name:"))
        if ok and name.strip():
            run_async(self, lambda: self.session.client.mkdir(self.area, self._rel(name.strip())),
                      lambda _r: self.refresh(), self._warn)

    def _warn(self, e: Exception) -> None:
        QMessageBox.warning(self, tr("Error"), tr_error(e))

    # ---- edit (administrators, or the owner in the personal area) ------
    def _rename(self) -> None:
        sel = self._selected()
        if len(sel) != 1:
            return QMessageBox.information(self, tr("Rename"), tr("Select a single item."))
        src = self._rel(sel[0]["name"])
        new, ok = QInputDialog.getText(self, tr("Rename/Move"), tr("New path (relative to the area):"), text=src)
        if ok and new.strip() and new.strip() != src:
            run_async(self, lambda: self.session.client.move(self.area, src, new.strip()),
                      lambda _r: self.refresh(), self._warn)

    def _delete(self) -> None:
        sel = self._selected()
        if not sel:
            return
        names = ", ".join(e["name"] for e in sel[:5]) + ("..." if len(sel) > 5 else "")
        if QMessageBox.question(self, tr("Delete"), tr("Permanently delete: {names}?", names=names)) \
                != QMessageBox.StandardButton.Yes:
            return

        def job() -> None:
            for e in sel:
                self.session.client.delete(self.area, self._rel(e["name"]))

        run_async(self, job, lambda _r: self.refresh(), self._warn)

    def _approve(self) -> None:
        sel = [e for e in self._selected() if e["type"] == "file"]
        if self.area != "models" or not self.path.startswith("_pending") or len(sel) != 1:
            return QMessageBox.information(self, tr("Approve"), tr("Open models/_pending/<user> and select a model."))
        rel = self._rel(sel[0]["name"])
        parts = rel.split("/")                                  # _pending/<user>/<species>/<file>
        default = "/".join(parts[2:]) if len(parts) > 2 else sel[0]["name"]
        name, ok = QInputDialog.getText(self, tr("Approve model"),
                                        tr("Publish as (path in the models folder, Genus species/file.pt):"),
                                        text=default)
        if ok and name.strip():
            run_async(self, lambda: self.session.client.approve(rel, name.strip()),
                      lambda _r: self.refresh(), self._warn)


class ServerBrowserDialog(QDialog):
    def __init__(self, session: Session, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Server folders"))
        self.resize(820, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(ServerBrowserWidget(session, parent=self))
