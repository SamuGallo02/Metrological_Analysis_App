"""The folders of this computer the application works with.

Two ways of looking at the same files, and nothing is ever copied from one to the other:

  Photos, stereo photos, videos, stereo videos   the animals, by species. The species of a file are the classes
                                                 of its labels, so a photo with two animals is under both.
  Datasets                                       the folders the user added, exactly as they were added (plus
                                                 the training datasets of the application). From here a file is
                                                 filed under a species with a label of its own.
  YOLO models                                    the models of the application.

The folders registered in "Datasets" are the ones the analysis offers, so a folder added here can be analysed
straight away; the files keep the names they have and no naming convention is asked for.

Autore: Samuele Gallo
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
from common.params import (AREA_GROUPS, AREA_MINE, ENHANCED_DIR, IMAGE_SUFFIXES, ORIGINALS_DIR,
                           STEREO_SIDES, VIDEO_SUFFIXES)
from common.species import UNNAMED, assign_many, by_species, forget as forget_species, known_species
from common.paths import MODELS_DIR, TRAINING_DIR
from common.ui.label_editor import edit_local_labels
from common.ui.label_overlay import with_labels
from common.ui.label_style import labels_visible, set_labels_visible
from common.ui.media_viewer import view_media
from common.ui.qt_utils import run_async
from common.ui.thumbnails import ThumbnailCache, can_preview
from common.ui.server_state import server_note, server_ready
from common.ui.places import desktop, managed

from corpse.functions.users.session import Session

from .enhance_dialog import improve_media, local_ready

SOURCE_ROLE = Qt.ItemDataRole.UserRole + 1                 # id of the registered folder, on its own row
SPECIES_ROLE = Qt.ItemDataRole.UserRole + 2                # species of a row, in the views by species
BY_SPECIES, PLAIN_FOLDER, ADDED_FOLDERS, ONLY_IMPROVED = "species", "folder", "sources", "improved"


def tabs() -> List[Tuple[str, str, str, Optional[Path]]]:
    """(name, what the tab shows, kind of the library, folder of the application).
    The media are shown by species; "Improved" gathers the improved copies, wherever their original is, and
    "Datasets" - the folders as the user added them - is always the last one."""
    return [(tr("Photos"), BY_SPECIES, KIND_PHOTO, None),
            (tr("Stereo photos"), BY_SPECIES, KIND_PHOTO_STEREO, None),
            (tr("Videos"), BY_SPECIES, KIND_VIDEO, None),
            (tr("Stereo videos"), BY_SPECIES, KIND_VIDEO_STEREO, None),
            (tr("Improved"), ONLY_IMPROVED, "", None),
            (tr("YOLO models"), PLAIN_FOLDER, "", MODELS_DIR),
            (tr("Datasets"), ADDED_FOLDERS, "", TRAINING_DIR)]


def kind_label(kind: str) -> str:
    return {KIND_PHOTO: tr("Photos"), KIND_PHOTO_STEREO: tr("Stereo photos"),
            KIND_VIDEO: tr("Videos"), KIND_VIDEO_STEREO: tr("Stereo videos")}.get(kind, kind)


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
        self._species_files: Dict[str, List[Path]] = {}     # the files of each species, filled on refresh
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<h3>{tr('Local folders')}</h3>"))
        hint = QLabel(tr("Photos and videos are shown by species, taken from their labels: a file with two animals "
                         "is under both. 'Datasets' holds the folders as you added them - from there you file a "
                         "file under a species, and those folders are the ones the analysis offers."))
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.tabs = QTabBar()
        for label, _mode, _kind, _folder in tabs():
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
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)   # several files at a time
        self.tree.itemExpanded.connect(self._expanded)
        self.tree.itemDoubleClicked.connect(lambda *_: self._open())
        self.tree.currentItemChanged.connect(lambda *_: self._update_buttons())
        self.tree.itemSelectionChanged.connect(self._update_buttons)
        lay.addWidget(self.tree, 1)

        folders = QHBoxLayout()
        self.btn_add_folder = self._button(folders, tr("Add folder..."), self._add_folder)
        self.btn_add_files = self._button(folders, tr("Add files..."), self._add_files)
        self.btn_new = self._button(folders, tr("New folder"), self._new_folder)
        self.btn_rename = self._button(folders, tr("Rename"), self._rename)
        self.btn_move = self._button(folders, tr("Move..."), self._move)
        self.btn_delete = self._button(folders, tr("Delete"), self._delete)
        folders.addStretch(1)
        lay.addLayout(folders)

        files = QHBoxLayout()
        self.btn_open = self._button(files, tr("Open"), self._open)
        self.labels_on = QCheckBox(tr("Labels"))
        self.labels_on.setChecked(labels_visible())
        self.labels_on.setToolTip(tr("Show the labels over the photos and videos, previews included."))
        self.labels_on.toggled.connect(self._labels_toggled)
        files.addWidget(self.labels_on)
        self.btn_labels = self._button(files, tr("Edit labels..."), self._edit_labels)
        self.btn_species = self._button(files, tr("File under a species..."), self._assign_species)
        self.btn_improve = self._button(files, tr("Improve..."), self._improve)
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
    def tab(self) -> Tuple[str, str, str, Optional[Path]]:
        return tabs()[max(0, self.tabs.currentIndex())]

    @property
    def mode(self) -> str:
        """What this tab shows: the species, a folder of the application, or the folders the user added."""
        return self.tab()[1]

    @property
    def kind(self) -> str:
        """The kind of the library shown, or "" where the tab is not about one kind."""
        return self.tab()[2]

    def app_folder(self) -> Optional[Path]:
        return self.tab()[3]

    def sources(self, kind: str = "") -> List[Source]:
        return self.library.sources(kind or self.kind) if (kind or self.kind) else []

    def files_of_kind(self, kind: str) -> List[Path]:
        """Every file of every folder registered for a kind, read from disk now."""
        return [f for src in self.sources(kind) if src.exists for f in self.library.files(src)]

    # ---- the tree ------------------------------------------------------
    def refresh(self) -> None:
        """Fills the tree the way this tab asks for: by species, one folder, or the folders the user added."""
        self.tree.clear()
        self._waiting.clear()
        self._species_files = {}
        self.tree.setColumnHidden(3, not self.labels_on.isChecked())
        {BY_SPECIES: self._fill_species, PLAIN_FOLDER: self._fill_folder,
         ADDED_FOLDERS: self._fill_sources, ONLY_IMPROVED: self._fill_improved}[self.mode]()
        self._update_buttons()

    def _fill_species(self) -> None:
        """The animals of this kind, grouped by the species their labels carry."""
        files = self.files_of_kind(self.kind)
        groups = by_species(files)
        self._species_files = groups
        names = sorted((n for n in groups if n), key=str.lower) + ([UNNAMED] if UNNAMED in groups else [])
        for name in names:
            node = QTreeWidgetItem([name or tr("Without a species"),
                                    tr("{n} files", n=len(groups[name])), "", ""])
            node.setData(0, SPECIES_ROLE, name)
            node.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            self.tree.addTopLevelItem(node)
        self.crumb.setText(tr("{n} species, {m} files", n=len([n for n in names if n]), m=len(files)))
        self.status.setText(tr("{n} species, {m} files", n=len([n for n in names if n]), m=len(files)) if files
                            else tr("No file yet: add the folders in 'Datasets'."))

    def _fill_improved(self) -> None:
        """Only the improved copies, of every kind, each one under the name of its original."""
        total = 0
        for kind in (KIND_PHOTO, KIND_PHOTO_STEREO, KIND_VIDEO, KIND_VIDEO_STEREO):
            pairs = [(f, find_enhanced(f)) for f in self.files_of_kind(kind)]
            pairs = [(original, copy) for original, copy in pairs if copy is not None]
            total += len(pairs)
            group = QTreeWidgetItem([kind_label(kind), tr("{n} files", n=len(pairs)), "", ""])
            self.tree.addTopLevelItem(group)
            for original, copy in pairs:
                try:
                    st = copy.stat()
                except OSError:
                    continue
                child = QTreeWidgetItem([copy.name, fmt_size(st.st_size), fmt_time(st.st_mtime),
                                         self._label_mark(original)])
                child.setData(0, Qt.ItemDataRole.UserRole, str(copy))
                child.setToolTip(0, tr("Improved copy of {path}", path=str(original)))
                if can_preview(copy.name):
                    icon = self.thumbs.icon(str(copy))
                    if icon is not None:
                        child.setIcon(0, icon)
                    else:
                        self._waiting.setdefault(str(copy), []).append(child)
                group.addChild(child)
            group.setExpanded(bool(pairs))
        self.crumb.setText(tr("The improved copies, beside their originals"))
        self.status.setText(tr("{n} files", n=total) if total
                            else tr("No improved copy yet: choose a file and press 'Improve...'."))

    def _fill_folder(self) -> None:
        """A folder of the application (the models), with what is inside it."""
        folder = self.app_folder()
        try:
            folder.mkdir(parents=True, exist_ok=True)       # a kind never used yet: show it empty, not missing
        except OSError:
            pass
        self.crumb.setText(str(folder))
        holder = QTreeWidgetItem()
        holder.setData(0, Qt.ItemDataRole.UserRole, str(folder))
        self._expanded(holder)
        while holder.childCount():
            self.tree.addTopLevelItem(holder.takeChild(0))
        self.status.setText(tr("{n} files", n=self.tree.topLevelItemCount()))

    def _fill_sources(self) -> None:
        """The folders the user added, as they were added, by kind - and the datasets of the application."""
        total = 0
        for kind in (KIND_PHOTO, KIND_PHOTO_STEREO, KIND_VIDEO, KIND_VIDEO_STEREO):
            sources = self.sources(kind)
            total += len(sources)
            group = QTreeWidgetItem([kind_label(kind), tr("{n} folders in the list", n=len(sources)), "", ""])
            group.setData(0, Qt.ItemDataRole.UserRole + 3, kind)
            self.tree.addTopLevelItem(group)
            for src in sources:
                item = QTreeWidgetItem([src.name, "", "" if src.exists else tr("folder not found"), ""])
                item.setData(0, Qt.ItemDataRole.UserRole, str(src.path))
                item.setData(0, SOURCE_ROLE, src.id)
                item.setToolTip(0, str(src.path))
                if src.exists:
                    item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                group.addChild(item)
            group.setExpanded(True)
        datasets = self.app_folder()
        try:
            datasets.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        built = QTreeWidgetItem([tr("Training datasets"), "", "", ""])
        built.setData(0, Qt.ItemDataRole.UserRole, str(datasets))
        built.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
        self.tree.addTopLevelItem(built)
        self.crumb.setText(str(datasets.parent))
        self.status.setText(tr("{n} folders in the list", n=total) if total
                            else tr("No folder yet: use 'Add folder...'."))

    def _expanded(self, item: QTreeWidgetItem) -> None:
        if item.childCount():
            return
        species = item.data(0, SPECIES_ROLE)
        if species is not None:
            return self._fill_species_files(item, species)
        where = self.path_of(item)
        if not where:                                    # a group of the Datasets tab: it has no folder of its own
            return
        folder = Path(where)
        try:
            children = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError as e:
            self.status.setText(tr("Error: {msg}", msg=str(e)))
            return
        for p in children:
            if p.name.startswith((".", "_")):            # what the application keeps for itself (_pending...)
                continue
            if p.is_dir() and p.name in (ENHANCED_DIR, ORIGINALS_DIR):
                continue                                 # the improved copy and the original it replaced are
                                                         # two ways of seeing one file: the viewer switches between
                                                         # them, so they are not folders of their own here
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

    def _fill_species_files(self, node: QTreeWidgetItem, species: str) -> None:
        """The files filed under a species: they stay where they are, this is only a way of looking at them."""
        for f in sorted(self._species_files.get(species, []), key=lambda p: str(p).lower()):
            try:
                st = f.stat()
            except OSError:
                continue
            child = QTreeWidgetItem([f.name, fmt_size(st.st_size), fmt_time(st.st_mtime), self._label_mark(f)])
            child.setData(0, Qt.ItemDataRole.UserRole, str(f))
            child.setToolTip(0, str(f))                      # where the file really is
            if can_preview(f.name):
                icon = self.thumbs.icon(str(f))
                if icon is not None:
                    child.setIcon(0, icon)
                else:
                    self._waiting.setdefault(str(f), []).append(child)
            node.addChild(child)

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
        """What is selected, or the folder of the tab when nothing is and the tab has one."""
        path = self.path_of(self.tree.currentItem())
        if path:
            return Path(path)
        return self.app_folder() if self.mode == PLAIN_FOLDER else None

    def chosen_media(self) -> List[Path]:
        """The photos or videos picked one by one: filing under a species works on these, not on a whole species
        (a species row stands for files that are already filed) and not on a folder."""
        out = []
        for item in self.tree.selectedItems():
            if item.data(0, SPECIES_ROLE) is not None:
                return []                                    # a species is chosen: nothing to file
            path = self.path_of(item)
            if not path or not Path(path).is_file() or not is_media(Path(path)):
                return []
            out.append(Path(path))
        return out

    def selected_files(self) -> List[Path]:
        """Every media file chosen in the tree (a species node brings all of its files)."""
        out: List[Path] = []
        for item in self.tree.selectedItems():
            species = item.data(0, SPECIES_ROLE)
            if species is not None:
                out.extend(self._species_files.get(species, []))
                continue
            path = self.path_of(item)
            if path and Path(path).is_file() and is_media(Path(path)):
                out.append(Path(path))
        seen, unique = set(), []
        for f in out:                                        # the same file can be under two species
            if str(f) not in seen:
                seen.add(str(f))
                unique.append(f)
        return unique

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
        """A button is on when there is something real to do it to: the row must be a file or a folder on disk
        (a species is only a way of looking at the files, so it cannot be renamed or deleted)."""
        path = self.current()
        chosen = path is not None
        source = self.current_source()
        media = chosen and path.is_file() and is_media(path)
        folder = chosen and path.is_dir()
        self.btn_add_folder.setEnabled(self.mode in (ADDED_FOLDERS, BY_SPECIES))   # there the kind is known
        self.btn_add_files.setEnabled(folder)
        self.btn_open.setEnabled(chosen)
        self.btn_new.setEnabled(folder)
        for b in (self.btn_rename, self.btn_move):
            b.setEnabled(chosen and not self._is_root(path) and source is None)    # not a folder of the list
        self.btn_delete.setEnabled(chosen and not self._is_root(path))             # a root is taken off the list
        self.btn_labels.setEnabled(media)
        self.btn_labels.setText(tr("Edit labels...") if media and find_labels(path) else tr("Create labels..."))
        self.btn_species.setEnabled(bool(self.chosen_media()))
        self.btn_improve.setEnabled(media and (local_ready() or server_ready(self.session)))
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
            forget_species(path)                          # the viewer can open the editor: read them again
            self.thumbs.forget(str(path))
            return self.refresh()
        try:
            open_in_system(path)
        except OSError as e:
            self._fail(e)

    # ---- the folders of the library --------------------------------------
    def chosen_kind(self) -> str:
        """The kind a new folder goes under: the one of the group that is selected, or asked for."""
        item = self.tree.currentItem()
        while item is not None:
            kind = item.data(0, Qt.ItemDataRole.UserRole + 3)
            if kind:
                return kind
            item = item.parent()
        kinds = [KIND_PHOTO, KIND_PHOTO_STEREO, KIND_VIDEO, KIND_VIDEO_STEREO]
        label, ok = QInputDialog.getItem(self, tr("Add folder..."), tr("What do these files hold?"),
                                         [kind_label(k) for k in kinds], 0, False)
        return kinds[[kind_label(k) for k in kinds].index(label)] if ok else ""

    def _add_folder(self) -> None:
        """Registers a folder of the computer where it is: nothing is copied, and the analysis sees it at once."""
        kind = self.kind or self.chosen_kind()
        if not kind:
            return
        start = self.sources(kind)
        initial = str(start[-1].path.parent) if start else desktop()   # a folder of yours: the Desktop first
        chosen = QFileDialog.getExistingDirectory(self, tr("Add folder..."), initial)
        if not chosen:
            return
        folder = Path(chosen)
        warning = stereo_warning(kind, folder)
        if warning and QMessageBox.question(self, tr("Add folder..."), warning + "\n\n" + tr("Add it anyway?")) \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            self.library.add_source(kind, folder)
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
        chosen, _ = QFileDialog.getOpenFileNames(self, tr("Add files..."), desktop(), pattern)
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
        dest = QFileDialog.getExistingDirectory(self, tr("Move..."),            # inside what the app manages
                                                managed(self.kind, path.parent))
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
        """Deletes what is chosen. A folder of the list is only taken off the list: its files stay where they are,
        because the application never owned them."""
        path = self.current()
        if path is None or self._is_root(path):
            return
        source_id = self.current_source()
        if source_id is not None:
            if QMessageBox.question(self, tr("Delete"),
                                    tr("Remove '{name}' from the list? The files in {path} are not touched.",
                                       name=path.name, path=str(path))) != QMessageBox.StandardButton.Yes:
                return
            self.library.remove_source(int(source_id))
            return self.refresh()
        question = tr("Delete the folder '{name}' and everything in it?", name=path.name) if path.is_dir() \
            else tr("Delete '{name}' from this computer?", name=path.name)
        if QMessageBox.question(self, tr("Delete"), question) != QMessageBox.StandardButton.Yes:
            return
        source = self.library.source_of(path)
        try:
            shutil.rmtree(path) if path.is_dir() else path.unlink()
        except OSError as e:
            return self._fail(e)
        if source is not None and source.path == path.resolve():
            self.library.remove_source(source.id)
        self.refresh()

    def _assign_species(self) -> None:
        """Files one or more chosen files under a species: a label of that species is added to each of them, so
        they appear in its view. The files are not moved, and a file can be under several species at once."""
        files = self.chosen_media()                      # the files picked one by one, never a whole species
        if not files:
            return
        here = known_species(self.files_of_kind(self.kind) if self.kind
                             else [f for k in (KIND_PHOTO, KIND_PHOTO_STEREO, KIND_VIDEO, KIND_VIDEO_STEREO)
                                   for f in self.files_of_kind(k)])
        name, ok = QInputDialog.getItem(self, tr("File under a species..."),
                                        tr("Species of these {n} files (a file can be under more than one):",
                                           n=len(files)), here, 0, True)
        name = (name or "").strip()
        if not ok or not name:
            return
        try:
            changed = assign_many(files, name)
        except OSError as e:
            return self._fail(e)
        self.status.setText(tr("{n} files filed under {name}", n=changed, name=name))
        if changed == 1 and len(files) == 1 and QMessageBox.question(
                self, tr("File under a species..."),
                tr("A label covering the whole picture was added. Do you want to draw it properly now?")) \
                == QMessageBox.StandardButton.Yes:
            edit_local_labels(self, files[0])
            forget_species(files[0])
        self.refresh()

    # ---- the labels and the improvement ----------------------------------
    def _edit_labels(self) -> None:
        path = self.current()
        if path is None or not path.is_file():
            return
        edit_local_labels(self, path)
        forget_species(path)                              # its species are read again: they may have changed
        self.thumbs.forget(str(path))
        self.refresh()

    def _improve(self) -> None:
        path = self.current()
        if path is not None and path.is_file():
            self._improve_file(path)

    def _improve_file(self, path: Path) -> None:
        kept = improve_media(self, self.session, Path(path))
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
