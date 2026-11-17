"""The folders of this computer the application works with.

They are the same kinds the server has - photos, stereo photos, videos, stereo videos, datasets and models - so
what is here and what is on the server read the same way. The media folders are the very ones the analysis
offers: a folder added here (with its files, and the labels that may already sit next to them - no naming
convention is asked for) can be chosen straight away in the analysis pages, and it is never copied, only pointed
at. Datasets and models live in the application's own folders.

Everything is done on the computer itself: open, add, rename, move, delete, look at the labels and correct them,
ask the server for the improved image, and send a file or a whole folder to the server.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QMessageBox, QPushButton, QTabBar, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from common.errors import AppError
from common.format import fmt_size, fmt_time
from common.i18n import tr, tr_error
from common.image_enhance import find_enhanced
from common.label_store import find_labels
from common.media_library import (KIND_PHOTO, KIND_PHOTO_STEREO, KIND_VIDEO, KIND_VIDEO_STEREO, LEGACY_DIRS,
                                  Source, default_registry, media_suffixes)
from common.params import AREA_GROUPS, AREA_MINE, IMAGE_SUFFIXES, STEREO_SIDES, VIDEO_SUFFIXES
from common.paths import MODELS_DIR, TRAINING_DIR
from common.ui.label_editor import edit_local_labels
from common.ui.label_overlay import with_labels
from common.ui.label_style import LabelColorButton, labels_visible, set_labels_visible
from common.ui.media_viewer import view_media
from common.ui.qt_utils import run_async
from common.ui.thumbnails import ThumbnailCache, can_preview
from common.ui.server_state import server_note, server_ready

from corpse.functions.users.session import Session

from .enhance_dialog import improve_with_server

SOURCE_ROLE = Qt.ItemDataRole.UserRole + 1                 # id of the registered folder, on its own row


def tabs() -> List[Tuple[str, str, Optional[Path]]]:
    """(name, kind of the library, folder of the application) of each tab, in the order of the server.
    The media kinds come from the library (any folder of the computer); the last two are folders of the app."""
    return [(tr("Photos"), KIND_PHOTO, None),
            (tr("Stereo photos"), KIND_PHOTO_STEREO, None),
            (tr("Videos"), KIND_VIDEO, None),
            (tr("Stereo videos"), KIND_VIDEO_STEREO, None),
            (tr("Datasets"), "", TRAINING_DIR),
            (tr("YOLO models"), "", MODELS_DIR)]


def is_media(path: Path) -> bool:
    return path.suffix.lower() in set(IMAGE_SUFFIXES) | set(VIDEO_SUFFIXES)


def stereo_warning(kind: str, folder: Path) -> str:
    """A stereo folder normally holds the two sides (rx/lx): says so, without refusing the folder."""
    if "stereo" not in kind:
        return ""
    names = {p.name.lower() for p in folder.iterdir() if p.is_dir()} if folder.is_dir() else set()
    if any(side in names for side in STEREO_SIDES):
        return ""
    return tr("This folder has no 'rx' and 'lx' subfolders: the stereo analysis may not be able to use it.")


def open_in_system(path: Path) -> None:
    """Opens a file or a folder with the program the system uses for it."""
    if sys.platform.startswith("win"):
        os.startfile(str(path))            # noqa: S606 - the path comes from the user's own folders
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class SendToServerDialog(QDialog):
    """Where a local file or folder goes on the server: your own folder, or one of your groups."""

    def __init__(self, session: Session, name: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle(tr("Send to the server"))
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("Where do you want to put '{name}'?", name=name)))
        self.where = QComboBox()
        self.where.addItem(tr("My folder"), (AREA_MINE, ""))
        for group in self.groups():
            self.where.addItem(tr("Group: {name}", name=group), (AREA_GROUPS, group))
        lay.addWidget(self.where)
        self.note = QLabel(tr("In a group where you are not an administrator, what you send waits for approval."))
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def groups(self) -> List[str]:
        try:
            return [g["name"] for g in self.session.client.groups()]
        except Exception:                                  # noqa: BLE001 - offline or server down: only "My folder"
            return []

    def destination(self) -> Dict[str, str]:
        area, group = self.where.currentData()
        return {"area": area, "prefix": group}


class LocalFoldersWidget(QWidget):
    """Tree of the local folders, with what can be done with them."""

    def __init__(self, session: Session, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        self.library = default_registry()
        self.thumbs = ThumbnailCache(lambda key: Path(key).read_bytes(),
                                     decorate=self._decorate, variant="labels" if labels_visible() else "")
        self.thumbs.ready.connect(self._thumb_ready)
        self._waiting: Dict[str, List[QTreeWidgetItem]] = {}
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<h3>{tr('Local folders')}</h3>"))
        hint = QLabel(tr("Your files on this computer, by kind, as on the server. The folders you add here are the "
                         "ones the analysis offers; the files keep the names they have."))
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.tabs = QTabBar()
        for label, _kind, _folder in tabs():
            self.tabs.addTab(label)
        self.tabs.currentChanged.connect(lambda *_: self.refresh())
        lay.addWidget(self.tabs)
        self.crumb = QLabel()
        lay.addWidget(self.crumb)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels([tr("Name"), tr("Size"), tr("Changed"), tr("Labels")])
        self.tree.setIconSize(self.thumbs.size_hint())
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.itemExpanded.connect(self._expanded)
        self.tree.itemDoubleClicked.connect(lambda *_: self._open())
        self.tree.currentItemChanged.connect(lambda *_: self._update_buttons())
        lay.addWidget(self.tree, 1)

        folders = QHBoxLayout()
        self.btn_add_folder = self._button(folders, tr("Add folder..."), self._add_folder)
        self.btn_add_files = self._button(folders, tr("Add files..."), self._add_files)
        self.btn_new = self._button(folders, tr("New folder"), self._new_folder)
        self.btn_rename = self._button(folders, tr("Rename"), self._rename)
        self.btn_move = self._button(folders, tr("Move..."), self._move)
        self.btn_delete = self._button(folders, tr("Delete"), self._delete)
        self.btn_forget = self._button(folders, tr("Remove from the list"), self._forget)
        folders.addStretch(1)
        lay.addLayout(folders)

        files = QHBoxLayout()
        self.btn_open = self._button(files, tr("Open"), self._open)
        self.labels_on = QCheckBox(tr("Labels"))
        self.labels_on.setChecked(labels_visible())
        self.labels_on.setToolTip(tr("Show the labels over the photos and videos, previews included."))
        self.labels_on.toggled.connect(self._labels_toggled)
        files.addWidget(self.labels_on)
        self.colour = LabelColorButton()
        self.colour.changed.connect(self.refresh)
        files.addWidget(self.colour)
        self.btn_labels = self._button(files, tr("Edit labels..."), self._edit_labels)
        self.btn_improve = self._button(files, tr("Improve with the server..."), self._improve)
        self.btn_send = self._button(files, tr("Send to the server..."), self._send)
        files.addStretch(1)
        self.btn_refresh = self._button(files, tr("Refresh"), self.refresh)
        lay.addLayout(files)
        self.status = QLabel("")
        lay.addWidget(self.status)
        self.refresh()

    def _decorate(self, key: str, image):
        """What the preview of a file shows besides the picture: its labels, when they are turned on."""
        if not self.labels_on.isChecked():
            return image
        return with_labels(image, Path(key))

    def _labels_toggled(self, on: bool) -> None:
        set_labels_visible(on)                      # one setting for every view and every preview
        self.thumbs.set_variant("labels" if on else "", self._decorate)
        self.refresh()

    def _button(self, row: QHBoxLayout, text: str, slot) -> QPushButton:
        b = QPushButton(text)
        b.clicked.connect(slot)
        row.addWidget(b)
        return b

    # ---- what the open tab is ------------------------------------------
    def tab(self) -> Tuple[str, str, Optional[Path]]:
        return tabs()[max(0, self.tabs.currentIndex())]

    @property
    def kind(self) -> str:
        """The kind of the library shown, or "" on the tabs of the application's own folders."""
        return self.tab()[1]

    def app_folder(self) -> Optional[Path]:
        return self.tab()[2]

    def sources(self) -> List[Source]:
        return self.library.sources(self.kind) if self.kind else []

    # ---- the tree ------------------------------------------------------
    def refresh(self) -> None:
        """Shows the registered folders of the kind, or the contents of the application's folder."""
        self.tree.clear()
        self._waiting.clear()
        self.tree.setColumnHidden(3, not self.labels_on.isChecked())
        folder = self.app_folder()
        if folder is not None:
            try:
                folder.mkdir(parents=True, exist_ok=True)   # a kind never used yet: show it empty, not missing
            except OSError:
                pass
            self.crumb.setText(str(folder))
            holder = QTreeWidgetItem()
            holder.setData(0, Qt.ItemDataRole.UserRole, str(folder))
            self._expanded(holder)
            while holder.childCount():
                self.tree.addTopLevelItem(holder.takeChild(0))
            self.status.setText(tr("{n} files", n=self.tree.topLevelItemCount()))
        else:
            sources = self.sources()
            self.crumb.setText(tr("{n} folders in the list", n=len(sources)))
            for src in sources:
                item = QTreeWidgetItem([src.name, "", "" if src.exists else tr("folder not found"), ""])
                item.setData(0, Qt.ItemDataRole.UserRole, str(src.path))
                item.setData(0, SOURCE_ROLE, src.id)
                item.setToolTip(0, str(src.path))
                if src.exists:
                    item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                self.tree.addTopLevelItem(item)
            self.status.setText(tr("{n} folders in the list", n=len(sources)) if sources
                                else tr("No folder yet: use 'Add folder...'."))
        self._update_buttons()

    def _expanded(self, item: QTreeWidgetItem) -> None:
        if item.childCount():
            return
        folder = Path(self.path_of(item) or "")
        try:
            children = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError as e:
            self.status.setText(tr("Error: {msg}", msg=str(e)))
            return
        for p in children:
            try:
                st = p.stat()
            except OSError:
                continue
            child = QTreeWidgetItem([p.name, "" if p.is_dir() else fmt_size(st.st_size), fmt_time(st.st_mtime),
                                     self._label_mark(p)])
            child.setData(0, Qt.ItemDataRole.UserRole, str(p))
            if p.is_dir():
                child.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            elif can_preview(p.name):
                icon = self.thumbs.icon(str(p))
                if icon is not None:
                    child.setIcon(0, icon)
                else:
                    self._waiting.setdefault(str(p), []).append(child)
            item.addChild(child)

    def _label_mark(self, path: Path) -> str:
        """What the "Labels" column says about a file: whether it has labels, and whether it has been improved."""
        if not self.labels_on.isChecked() or path.is_dir() or not is_media(path):
            return ""
        marks = []
        if find_labels(path):
            marks.append(tr("labels"))
        if find_enhanced(path):
            marks.append(tr("improved"))
        return ", ".join(marks)

    def _thumb_ready(self, key: str, icon: QIcon) -> None:
        for item in self._waiting.pop(key, []):
            try:
                item.setIcon(0, icon)
            except RuntimeError:                           # the row is gone (folder reloaded)
                pass

    @staticmethod
    def path_of(item: Optional[QTreeWidgetItem]) -> str:
        return item.data(0, Qt.ItemDataRole.UserRole) if item is not None else ""

    def current(self) -> Optional[Path]:
        """What is selected, or the application's folder when nothing is on a tab that has one."""
        path = self.path_of(self.tree.currentItem())
        return Path(path) if path else self.app_folder()

    def current_source(self) -> Optional[int]:
        """The id of the registered folder, when a registered folder itself is selected."""
        item = self.tree.currentItem()
        return item.data(0, SOURCE_ROLE) if item is not None else None

    def _is_root(self, path: Optional[Path]) -> bool:
        """A folder that cannot be renamed, moved or deleted from here: the application's own folder of the kind."""
        return path is not None and path == self.app_folder()

    def _in_app_folders(self, path: Path) -> bool:
        """Inside one of the folders the application keeps for itself (there, deleting is safe)."""
        roots = list(LEGACY_DIRS.values()) + [TRAINING_DIR, MODELS_DIR]
        return any(root == path or root in path.parents for root in roots)

    def _update_buttons(self) -> None:
        path = self.current()
        chosen = path is not None
        source = self.current_source()
        media = chosen and path.is_file() and is_media(path)
        self.btn_add_folder.setEnabled(bool(self.kind))
        self.btn_add_files.setEnabled(chosen and path.is_dir())
        self.btn_open.setEnabled(chosen)
        self.btn_new.setEnabled(chosen and path.is_dir())
        for b in (self.btn_rename, self.btn_move, self.btn_delete):
            b.setEnabled(chosen and not self._is_root(path) and (source is None or self._in_app_folders(path)))
        self.btn_forget.setEnabled(source is not None and not self._in_app_folders(path))
        self.btn_labels.setEnabled(media)
        self.btn_labels.setText(tr("Edit labels...") if media and find_labels(path) else tr("Create labels..."))
        self.btn_improve.setEnabled(media and server_ready(self.session))
        self.btn_send.setEnabled(chosen and server_ready(self.session))

    # ---- the actions ----------------------------------------------------
    def _fail(self, error: Exception) -> None:
        QMessageBox.warning(self, tr("Local folders"), tr_error(error) if isinstance(error, AppError) else str(error))

    def _open(self) -> None:
        path = self.current()
        if path is None:
            return
        if path.is_file() and is_media(path):
            view_media(self, path, self.labels_on.isChecked(), self._improve_file)
            return self.refresh()
        try:
            open_in_system(path)
        except OSError as e:
            self._fail(e)

    # ---- the folders of the library --------------------------------------
    def _add_folder(self) -> None:
        """Registers a folder of the computer where it is: nothing is copied, and the analysis sees it at once."""
        if not self.kind:
            return
        start = self.sources()
        initial = str(start[-1].path.parent) if start else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, tr("Add folder..."), initial)
        if not chosen:
            return
        folder = Path(chosen)
        warning = stereo_warning(self.kind, folder)
        if warning and QMessageBox.question(self, tr("Add folder..."), warning + "\n\n" + tr("Add it anyway?")) \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            self.library.add_source(self.kind, folder)
        except (OSError, ValueError) as e:
            return self._fail(e)
        self.refresh()

    def _add_files(self) -> None:
        """Copies files chosen anywhere on the computer into the folder that is open."""
        path = self.current()
        if path is None or not path.is_dir():
            return
        suffixes = sorted(media_suffixes(self.kind)) if self.kind else []
        pattern = tr("Files") + " (" + " ".join(f"*{s}" for s in suffixes) + ")" if suffixes else tr("All files (*)")
        chosen, _ = QFileDialog.getOpenFileNames(self, tr("Add files..."), str(Path.home()), pattern)
        copied = 0
        for name in chosen:
            source = Path(name)
            dest = path / source.name
            n = 2
            while dest.exists():                            # never write over a file that is already there
                dest = path / f"{source.stem} ({n}){source.suffix}"
                n += 1
            try:
                shutil.copy2(source, dest)
                labels = source.with_suffix(".txt")         # labels already next to the file travel with it
                if labels.is_file():
                    shutil.copy2(labels, dest.with_suffix(".txt"))
                copied += 1
            except OSError as e:
                self._fail(e)
                break
        if copied:
            self.status.setText(tr("{n} files added", n=copied))
            self.refresh()

    def _forget(self) -> None:
        """Takes a folder out of the list. The files on disk are not touched."""
        source_id, path = self.current_source(), self.current()
        if source_id is None or path is None:
            return
        if QMessageBox.question(self, tr("Remove from the list"),
                                tr("Remove '{name}' from the list? The files in {path} are not touched.",
                                   name=path.name, path=str(path))) != QMessageBox.StandardButton.Yes:
            return
        self.library.remove_source(int(source_id))
        self.refresh()

    def _new_folder(self) -> None:
        path = self.current()
        if path is None or not path.is_dir():
            return
        name, ok = QInputDialog.getText(self, tr("New folder"), tr("Name of the folder"))
        if ok and name.strip():
            try:
                (path / name.strip()).mkdir(parents=True, exist_ok=False)
            except OSError as e:
                return self._fail(e)
            self.refresh()

    def _rename(self) -> None:
        path = self.current()
        if path is None or self._is_root(path):
            return
        name, ok = QInputDialog.getText(self, tr("Rename"), tr("New name"), text=path.name)
        if ok and name.strip() and name.strip() != path.name:
            target = path.with_name(name.strip())
            try:
                path.rename(target)
            except OSError as e:
                return self._fail(e)
            self._follow(path, target)
            self.refresh()

    def _move(self) -> None:
        path = self.current()
        if path is None or self._is_root(path):
            return
        dest = QFileDialog.getExistingDirectory(self, tr("Move..."), str(path.parent))
        if not dest:
            return
        target = Path(dest) / path.name
        try:
            shutil.move(str(path), str(target))
        except (OSError, shutil.Error) as e:
            return self._fail(e)
        self._follow(path, target)
        self.refresh()

    def _follow(self, old: Path, new: Path) -> None:
        """Keeps the list right when a registered folder is renamed or moved on disk."""
        source = self.library.source_of(old)
        if source is not None and source.path == old.resolve():
            self.library.move_source(source.id, new)

    def _delete(self) -> None:
        path = self.current()
        if path is None or self._is_root(path):
            return
        if QMessageBox.question(self, tr("Delete"),
                                tr("Delete '{name}' from this computer?", name=path.name)) \
                != QMessageBox.StandardButton.Yes:
            return
        source = self.library.source_of(path)
        try:
            shutil.rmtree(path) if path.is_dir() else path.unlink()
        except OSError as e:
            return self._fail(e)
        if source is not None and source.path == path.resolve():
            self.library.remove_source(source.id)
        self.refresh()

    # ---- the labels and the improvement ----------------------------------
    def _edit_labels(self) -> None:
        path = self.current()
        if path is None or not path.is_file():
            return
        edit_local_labels(self, path)
        self.refresh()

    def _improve(self) -> None:
        path = self.current()
        if path is not None and path.is_file():
            self._improve_file(path)

    def _improve_file(self, path: Path) -> None:
        kept = improve_with_server(self, self.session, Path(path))
        if kept is not None:
            self.status.setText(tr("Improved file saved in {path}", path=str(kept.parent)))
            self.refresh()

    # ---- to the server --------------------------------------------------
    def _send(self) -> None:
        path = self.current()
        if path is None:
            return
        dialog = SendToServerDialog(self.session, path.name, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        where = dialog.destination()
        self.status.setText(tr("Loading..."))
        run_async(self, lambda: self._upload(path, where), self._sent,
                  lambda e: (self.status.setText(""), self._fail(e)))

    def _upload(self, path: Path, where: Dict[str, str]) -> Dict[str, Any]:
        """Sends a file, or every file of a folder keeping the names inside it."""
        files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
        base = path.parent
        pending = 0
        for f in files:
            rel = f.relative_to(base).as_posix()
            remote = f"{where['prefix']}/{rel}" if where["prefix"] else rel
            result = self.session.client.upload(where["area"], remote, f)
            pending += 1 if result.get("pending") else 0
        return {"files": len(files), "pending": pending}

    def _sent(self, result: Dict[str, Any]) -> None:
        if result["pending"]:
            self.status.setText(tr("{n} files sent, waiting for approval", n=result["pending"]))
        else:
            self.status.setText(tr("{n} files sent", n=result["files"]))
