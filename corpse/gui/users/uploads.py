"""Uploads page of the user: three large buttons, one per kind. Whatever is sent waits for an administrator."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

from PySide6.QtWidgets import QFileDialog, QInputDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from common.i18n import tr, tr_error
from common.params import AREA_SPECIES, SPECIES_EXAMPLE, SPECIES_RE
from common.ui.qt_utils import run_async
from corpse.functions.users.session import Session
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
        self.btn_photos = self._big(tr("Upload photos of a species"), self._photos, lay)
        self.btn_dataset = self._big(tr("Upload a dataset"), self._dataset, lay)
        self.btn_model = self._big(tr("Upload a YOLO model"), self._model, lay)
        self.status = QLabel("")
        lay.addWidget(self.status)

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

    def _ask_species(self) -> Optional[str]:
        text = tr("Enter the scientific name as 'Genus species', for example {example}.", example=SPECIES_EXAMPLE)
        name, ok = QInputDialog.getText(self, tr("Scientific name"), text)
        name = name.strip()
        if not ok or not name:
            return None
        if not _is_species(name):
            QMessageBox.warning(self, tr("Scientific name"), text)
            return None
        return name

    def _photos(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Choose the folder to upload"))
        if not d:
            return
        root = Path(d)
        species = root.name if _is_species(root.name) else self._ask_species()
        if not species:
            return
        pairs = [(p, f"{species}/{p.name}") for p in _files(root, False)]
        self._send(AREA_SPECIES, pairs, species, lambda: self.session.client.submit_species(species))

    def _dataset(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Choose the folder to upload"))
        if not d:
            return
        root = Path(d)
        pairs = [(p, f"{root.name}/{p.relative_to(root).as_posix()}") for p in _files(root, True)]
        self._send("datasets", pairs, root.name, lambda: self.session.client.submit_dataset(root.name))

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
        self._send("models", pairs, species, lambda: self.session.client.submit_model(species, model.name))