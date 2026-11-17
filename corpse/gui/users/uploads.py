"""Uploads page of the user: one large button per kind of upload. Whatever is sent waits for an administrator."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from common.i18n import tr, tr_error
from common.species import common_species
from common.params import AREA_STEREO, AREA_STEREO_VIDEOS, AREA_VIDEOS, IMAGE_SUFFIXES, SPECIES_EXAMPLE, SPECIES_RE, VIDEO_SUFFIXES
from common.ui.qt_utils import run_async
from common.ui.server_state import server_note, server_ready
from corpse.functions.users.session import Session
from corpse.functions.users.upload_plan import has_stereo_folders, plan_media, plan_stereo
from .transfer import TransferDialog


def _files(root: Path, recursive: bool) -> List[Path]:
    found = root.rglob("*") if recursive else root.iterdir()
    return sorted(p for p in found if p.is_file() and not p.name.startswith("."))

def _is_species(name: str) -> bool:
    return re.fullmatch(SPECIES_RE, name) is not None

class UploadsWidget(QWidget):
    def __init__(self, session: Session, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        lay = QVBoxLayout(self)
        hint = QLabel(tr("Everything you send is checked by an administrator before it is published."))
        hint.setWordWrap(True)
        lay.addWidget(hint)
        row = QHBoxLayout()                                   # who signs what is published
        row.addWidget(QLabel(tr("Publish as:")))
        self.author = QComboBox()
        self.author.addItem(tr("Myself"), "")
        self.author.setToolTip(tr("Publishing for a work group: the group is the author in the catalog."))
        row.addWidget(self.author, 1)
        row.addStretch(1)
        lay.addLayout(row)
        self._load_groups()
        self.btn_photos = self._big(tr("Upload photos or videos of a species"), self._photos, lay)
        self.btn_stereo = self._big(tr("Upload stereo photos or videos"), self._stereo, lay)
        self.btn_dataset = self._big(tr("Upload a dataset"), self._dataset, lay)
        self.btn_model = self._big(tr("Upload a YOLO model"), self._model, lay)
        self.status = QLabel("")
        lay.addWidget(self.status)

    def _load_groups(self) -> None:
        """The work groups the user belongs to: they can publish in the name of the group."""
        if not server_ready(self.session):
            return

        def done(groups: List[Dict[str, Any]]) -> None:
            for g in groups:
                self.author.addItem(tr("Group: {name}", name=g["name"]), g["name"])

        run_async(self, self.session.client.groups, done, lambda _e: None)

    def group(self) -> str:
        """The group chosen to sign the upload ("" = the user themselves)."""
        return self.author.currentData() or ""

    @staticmethod
    def _big(text: str, slot: Callable[[], None], lay: QVBoxLayout) -> QPushButton:
        b = QPushButton(text)
        b.setMinimumHeight(90)
        b.setStyleSheet("font-size: 16px;")
        b.clicked.connect(slot)
        lay.addWidget(b, 1)
        return b

    def _fail(self, e: Exception) -> None:
        QMessageBox.warning(self, tr("Error"), tr_error(e))

    def _send(self, area: str, pairs: List[Tuple[Path, str]], name: str, submit: Callable[[], Any]) -> None:
        """Uploads the files with a progress window and, if everything went well, sends them to review."""
        if not pairs:
            return
        jobs = [(remote, local.stat().st_size, lambda cb, cancel, l=local, r=remote:
                 self.session.client.upload(area, r, l, cb, cancel)) for local, remote in pairs]
        dlg = TransferDialog(tr("Upload"), jobs, self)
        dlg.exec()
        if dlg.cancelled:
            return
        if dlg.errors:
            QMessageBox.warning(self, tr("Transfer"), tr("Errors:") + "\n" + "\n".join(dlg.errors[:8]))
            return
        run_async(self, submit, lambda _r: self.status.setText(tr("Sent for review: {name}.", name=name)), self._fail)

    def _ask_species(self, suggested: str = "") -> Optional[str]:
        """The species of what is being sent. The labels of the files already say it, when they agree."""
        text = tr("Enter the scientific name as 'Genus species', for example {example}.", example=SPECIES_EXAMPLE)
        name, ok = QInputDialog.getText(self, tr("Scientific name"), text, text=suggested)
        name = name.strip()
        if not ok or not name:
            return None
        if not _is_species(name):
            QMessageBox.warning(self, tr("Scientific name"), text)
            return None
        return name

    def _photos(self) -> None:
        """One photo or many, and videos, picked together (even from different folders), for one species. A label
        file with the same name next to a photo or saved by the analysis goes with it."""
        patterns = " ".join(f"*{ext}" for ext in sorted(IMAGE_SUFFIXES + VIDEO_SUFFIXES))
        files, _ = QFileDialog.getOpenFileNames(self, tr("Choose the photos to upload"), "",
                                                f"{tr('Photos')} ({patterns})")
        if not files:
            return
        chosen = [Path(f) for f in files]
        parent = chosen[0].parent.name
        species = parent if _is_species(parent) and all(c.parent == chosen[0].parent for c in chosen) \
            else self._ask_species(common_species(chosen))      # the labels of the files know it already
        if not species:
            return
        plan = plan_media(chosen, species)
        if not plan:
            QMessageBox.warning(self, tr("Error"), tr("No photos or videos among the chosen files."))
            return
        for area, pairs in plan.items():                         # photos and videos are separate uploads
            kind = "video" if area == AREA_VIDEOS else "photos"
            self._send(area, pairs, species,
                       lambda k=kind: self.session.client.submit_species(species, k, self.group()))

    def _stereo(self) -> None:
        """A folder with an `lx` and an `rx` subfolder holding photos (or videos) of the same names."""
        d = QFileDialog.getExistingDirectory(self, tr("Choose the folder with the lx and rx subfolders"))
        if not d:
            return
        root = Path(d)
        if not has_stereo_folders(root):
            QMessageBox.warning(self, tr("Error"), tr("The folder must contain an lx and an rx subfolder."))
            return
        species = root.name if _is_species(root.name) else \
            self._ask_species(common_species(sorted(p for p in root.rglob("*") if p.is_file())))
        if not species:
            return
        try:
            area, pairs = plan_stereo(root, species)
        except ValueError:
            QMessageBox.warning(self, tr("Error"), tr("A stereo folder holds either photos or videos, not both."))
            return
        if not pairs:
            QMessageBox.warning(self, tr("Error"), tr("No photos or videos among the chosen files."))
            return
        kind = "stereo_video" if area == AREA_STEREO_VIDEOS else "stereo"
        self._send(area, pairs, species,
                   lambda: self.session.client.submit_species(species, kind, self.group()))

    def _dataset(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Choose the folder to upload"))
        if not d:
            return
        root = Path(d)
        pairs = [(p, f"{root.name}/{p.relative_to(root).as_posix()}") for p in _files(root, True)]
        self._send("datasets", pairs, root.name,
                   lambda: self.session.client.submit_dataset(root.name, self.group()))

    def _model(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, tr("Choose the files to upload"), "", "YOLO (*.pt)")
        if not f:
            return
        model = Path(f)
        species = self._ask_species()
        if not species:
            return
        pairs = [(model, f"{species}/{model.name}")]
        details = model.with_suffix(".json")                     # DA VERIFICARE con il grep qui sotto
        if details.is_file():
            pairs.append((details, f"{species}/{details.name}"))
        self._send("models", pairs, species,
                   lambda: self.session.client.submit_model(species, model.name, self.group()))