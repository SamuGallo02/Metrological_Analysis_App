"""Browse the server folders. Common areas: everyone reads and uploads, only the 'server' role edits or
deletes. Personal area ('mine'): the owner can do everything, within the quota."""
from __future__ import annotations
import re

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QMessageBox, QProgressBar, QPushButton, QTabBar, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget, QTabWidget)

from common.format import fmt_size, fmt_time
from common.i18n import tr, tr_error

from common.params import AREA_MINE, AREAS_SHARED, SPECIES_EXAMPLE, SPECIES_RE
from common.ui.qt_utils import run_async
from common.remote_tree import walk_remote
from common.model_metadata import fetch_remote_metadata

from corpse.functions.users.session import Session
from .labels import PENDING_DIR, area_label, folder_label, path_label
from .transfer import TransferDialog
from .model_info import model_info_lines
from .uploads import UploadsWidget
from .catalog import CatalogWidget


class ServerBrowserWidget(QWidget):
    def __init__(self, session: Session, areas: Sequence[str] = AREAS_SHARED, parent: Optional[QWidget] = None,
                 download_only: bool = False):
        super().__init__(parent)
        self.session = session
        self.download_only = download_only            # only browse and download: no upload, no changes
        self.areas = tuple(areas)
        self.area, self.path = self.areas[0], ""
        self._info_token = 0                          # numero dell'ultima richiesta dei dettagli: scarta le risposte in ritardo
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
        self.tree.setRootIsDecorated(True)                        # always a tree: folders open in place, on demand
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.itemExpanded.connect(self._expanded)
        lay.addWidget(self.tree, 1)

        self.info = QLabel()                          # dettagli del modello selezionato (solo nella scheda dei modelli)
        self.info.setTextFormat(Qt.TextFormat.PlainText)
        self.info.setWordWrap(True)
        self.info.hide()
        lay.addWidget(self.info)
        self.tree.itemSelectionChanged.connect(self._show_info)

        row = QHBoxLayout()
        self.btn_refresh = self._btn(tr("Refresh"), self.refresh, row)
        self.btn_collapse = self._btn(tr("Collapse all"), self.tree.collapseAll, row)
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
        editing = not self.download_only
        self.btn_up_files.setVisible(editing)
        self.btn_up_dir.setVisible(editing)
        self.btn_mkdir.setVisible(editing)
        self.btn_rename.setVisible(editing and self._can_modify())
        self.btn_delete.setVisible(editing and self._can_modify())
        self.btn_approve.setVisible(editing and self.session.can("models.approve") and self.area == "models")
        self.btn_mkdir.setEnabled(self.session.online)
        self._update_note()

    def _update_note(self) -> None:
        if not self.session.online:
            text = f"<i>{tr('You are offline: the server folders are not available.')}</i>"
        elif self.download_only:
            text = tr("You can browse and download what the other users have shared.")
        elif self.area == AREA_MINE:
            text = tr("Your personal folder on the server: only you can see it. You can add, "
                      "rename, move and delete.")
        elif self.session.is_admin:
            text = tr("As an administrator you can modify and delete.")
            if self.area == "models":
                text += " " + tr("Models in the <b>{folder}</b> folder are waiting for approval.",
                                folder=folder_label(PENDING_DIR))
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
        """The selected entries; each has "path", its full path inside the area."""
        return [d for d in (it.data(0, Qt.ItemDataRole.UserRole) for it in self.tree.selectedItems()) if d]

    def _target(self) -> str:
        """Where uploads and new folders go: the selected folder (or the folder of the selected file),
        otherwise the folder the tree starts from."""
        sel = self._selected()
        if len(sel) != 1:
            return self.path
        path = sel[0]["path"]
        if sel[0]["type"] == "dir":
            return path
        return path.rsplit("/", 1)[0] if "/" in path else ""

    def _show_info(self) -> None:
        """Dettagli del modello selezionato: i metadati (.json) accanto al file, nella scheda dei modelli."""
        self._info_token += 1
        token, area = self._info_token, self.area
        sel = self._selected()
        is_model = (len(sel) == 1 and sel[0]["type"] == "file"
                    and sel[0]["name"].lower().endswith((".pt", ".onnx")))
        if area != "models" or not is_model:
            self.info.hide()
            return
        rel = sel[0]["path"]
        self.info.setText(tr("Loading..."))
        self.info.show()

        def done(meta: Optional[Dict[str, Any]]) -> None:
            if token == self._info_token:                      # nel frattempo la selezione è cambiata: si scarta
                self.info.setText("\n".join(model_info_lines(meta)))

        run_async(self, lambda: fetch_remote_metadata(self.session.client, area, rel), done,
                  lambda _e: done(None))

    @staticmethod
    def _rel_in(folder: str, name: str) -> str:
        return f"{folder}/{name}" if folder else name

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

    # ---- tree ------------------------------------------------------------
    def refresh(self) -> None:
        self.crumb.setText(f"<b>{area_label(self.area)}</b> / {path_label(self.path)}")
        self.tree.clear()
        if not self.session.online:
            self.status.setText(tr("Offline."))
            return
        self.status.setText(tr("Loading..."))
        self._refresh_quota()
        self._load(None, self.path)

    def _load(self, parent: Optional[QTreeWidgetItem], path: str) -> None:
        """Lists `path` and puts its entries under `parent` (None: at the top of the tree)."""
        area, root = self.area, self.path

        def done(entries: List[Dict[str, Any]]) -> None:
            if (area, root) != (self.area, self.path):             # the tree was reloaded or changed area meanwhile
                return
            if not path:                       # the folder of the waiting items is not shown: they are reviewed in Review
                entries = [e for e in entries if not (e["type"] == "dir" and e["name"] == PENDING_DIR)]
            if parent is not None:
                parent.takeChildren()
                if not entries:
                    parent.addChild(QTreeWidgetItem([tr("(empty)"), "", "", ""]))
            elif self.tree.topLevelItemCount():
                self.tree.clear()
            for e in sorted(entries, key=lambda e: (e["type"] != "dir", e["name"].lower())):
                is_dir = e["type"] == "dir"
                entry = dict(e, path=f"{path}/{e['name']}" if path else e["name"])
                shown = folder_label(e["name"]) if is_dir else e["name"]
                it = QTreeWidgetItem([(tr("[folder] ") if is_dir else "") + shown,
                                      tr("Folder") if is_dir else tr("File"),
                                      "" if is_dir else fmt_size(e["size"]), fmt_time(e["mtime"])])
                it.setData(0, Qt.ItemDataRole.UserRole, entry)
                if is_dir:
                    it.addChild(QTreeWidgetItem([tr("Loading..."), "", "", ""]))      # placeholder: shows the arrow
                if parent is None:
                    self.tree.addTopLevelItem(it)
                else:
                    parent.addChild(it)
            self.status.setText(tr("{n} items", n=len(entries)))

        def fail(e: Exception) -> None:
            if parent is not None:
                parent.takeChildren()
                parent.setData(0, Qt.ItemDataRole.UserRole, dict(parent.data(0, Qt.ItemDataRole.UserRole), loaded=False))
            self.status.setText(tr("Error: {msg}", msg=tr_error(e)))

        run_async(self, lambda: self.session.client.list(area, path), done, fail)

    def _expanded(self, item: QTreeWidgetItem) -> None:
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if not entry or entry["type"] != "dir" or entry.get("loaded"):
            return
        item.setData(0, Qt.ItemDataRole.UserRole, dict(entry, loaded=True))          # one request per folder
        self._load(item, entry["path"])

    def _reload(self, path: str) -> None:
        """Lists `path` again, keeping the rest of the tree as it is."""
        if not path or path == self.path:
            return self.refresh()
        stack = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        while stack:
            it = stack.pop()
            entry = it.data(0, Qt.ItemDataRole.UserRole)
            if entry and entry["type"] == "dir":
                if entry["path"] == path:
                    if it.isExpanded() or entry.get("loaded"):
                        it.setData(0, Qt.ItemDataRole.UserRole, dict(entry, loaded=True))
                        return self._load(it, path)
                    return
                if it.isExpanded():
                    stack.extend(it.child(i) for i in range(it.childCount()))
        self.refresh()

    def _goto(self, area: str, path: str) -> None:
        """Starts the tree from `path` of `area`."""
        if area in self.areas:
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(self.areas.index(area))
            self.tabs.blockSignals(False)
            self.area, self.path = area, path
            self._apply_role()
            self.refresh()

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

        def plan() -> List[Tuple[str, int, str]]:
            items: List[Tuple[str, int, str]] = []                # (path, size, folder it is saved relative to)
            for e in sel:
                parent = e["path"].rsplit("/", 1)[0] if "/" in e["path"] else ""
                if e["type"] == "dir":
                    items.extend((rel, size, parent) for rel, size in walk_remote(self.session.client, self.area, e["path"]))
                else:
                    items.append((e["path"], e["size"], parent))
            return items

        def go(items: List[Tuple[str, int, str]]) -> None:
            jobs = []
            for rel, size, base in items:
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

    def _upload_paths(self, pairs: List[Tuple[Path, str]], target: Optional[str] = None) -> None:
        self._upload_target = self.path if target is None else target
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
        self._reload(self._upload_target)

    def _upload_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, tr("Choose the files to upload"), self._start_dir())
        target = self._target()
        self._upload_paths([(Path(f), self._rel_in(target, Path(f).name)) for f in files], target)

    def _upload_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Choose the folder to upload"), self._start_dir())
        if not d:
            return
        root, target = Path(d), self._target()
        self._upload_paths([(p, self._rel_in(target, f"{root.name}/{p.relative_to(root).as_posix()}"))
                            for p in sorted(root.rglob("*")) if p.is_file()], target)

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
            target = self._target()
            run_async(self, lambda: self.session.client.mkdir(self.area, self._rel_in(target, name.strip())),
                      lambda _r: self._reload(target), self._warn)

    def _warn(self, e: Exception) -> None:
        QMessageBox.warning(self, tr("Error"), tr_error(e))

    # ---- edit (administrators, or the owner in the personal area) ------
    def _rename(self) -> None:
        sel = self._selected()
        if len(sel) != 1:
            return QMessageBox.information(self, tr("Rename"), tr("Select a single item."))
        src = sel[0]["path"]
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
                self.session.client.delete(self.area, e["path"])

        run_async(self, job, lambda _r: self.refresh(), self._warn)

    def _approve(self) -> None:
        sel = [e for e in self._selected() if e["type"] == "file"]
        if self.area != "models" or len(sel) != 1 or not sel[0]["path"].startswith(PENDING_DIR):
            return QMessageBox.information(self, tr("Approve"), tr("Open the {folder} folder, then the user's folder, and select a model.",
                                            folder=folder_label(PENDING_DIR)))
        rel = sel[0]["path"]
        parts = rel.split("/")                                  # _pending/<user>/<species>/<file>
        default = "/".join(parts[2:]) if len(parts) > 2 else sel[0]["name"]
        name, ok = QInputDialog.getText(self, tr("Approve model"),
                                        tr("Publish as (path in the models folder, Genus species/file.pt):"),
                                        text=default)
        if ok and name.strip():
            run_async(self, lambda: self.session.client.approve(rel, name.strip()),
                      lambda _r: self.refresh(), self._warn)


class ServerFoldersWidget(QWidget):
    def __init__(self, session: Session, parent: Optional[QWidget] = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        self.photos = CatalogWidget(session, "photos")
        self.stereo = CatalogWidget(session, "stereo")
        self.videos = CatalogWidget(session, "video")
        self.stereo_videos = CatalogWidget(session, "stereo_video")
        self.models = CatalogWidget(session, "model")
        self.uploads = UploadsWidget(session)                                 # filled in the next blocks
        self.tabs = QTabWidget()
        self.tabs.addTab(self.photos, tr("Photos"))
        self.tabs.addTab(self.stereo, tr("Stereo photos"))
        self.tabs.addTab(self.videos, tr("Videos"))
        self.tabs.addTab(self.stereo_videos, tr("Stereo videos"))
        self.tabs.addTab(self.models, tr("YOLO models"))
        self.tabs.addTab(self.uploads, tr("Uploads"))
        lay.addWidget(self.tabs)
