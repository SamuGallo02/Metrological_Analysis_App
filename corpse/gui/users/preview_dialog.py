"""Anteprima di un invio nella Revisione: miniature per foto e dataset, dettagli per un modello."""
from __future__ import annotations

import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QListView, QListWidget, QListWidgetItem,
                               QVBoxLayout, QWidget)

from common.i18n import tr, tr_error
from common.model_metadata import fetch_remote_metadata
from common.ui.qt_utils import run_async
from corpse.functions.users.preview import list_preview
from .model_info import model_info_lines

THUMB = 140
AREAS = {"photos": "species", "dataset": "datasets", "model": "models"}


class PreviewDialog(QDialog):
    """`sub` è una riga di invio (serve il suo `path`, relativo all'area del suo tipo)."""

    def __init__(self, client: Any, kind: str, sub: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.client, self.kind, self.sub = client, kind, sub
        self._tmp = tempfile.TemporaryDirectory()                # le miniature sono scaricate qui e spariscono con la finestra
        self.setWindowTitle(tr("Preview"))
        self.resize(720, 520)
        lay = QVBoxLayout(self)
        self.info = QLabel(tr("Loading..."))
        self.info.setTextFormat(Qt.TextFormat.PlainText)         # testo preso dal server: mai interpretato come HTML
        self.info.setWordWrap(True)
        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListView.ViewMode.IconMode)
        self.thumbs.setResizeMode(QListView.ResizeMode.Adjust)
        self.thumbs.setMovement(QListView.Movement.Static)
        self.thumbs.setIconSize(QSize(THUMB, THUMB))
        self.thumbs.setHidden(kind == "model")                   # un modello non ha immagini
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay.addWidget(self.info)
        lay.addWidget(self.thumbs, 1)
        lay.addWidget(buttons)
        if kind == "model":
            run_async(self, self._load_model, self._show_model, self._failed)
        else:
            run_async(self, self._load_images, self._show_images, self._failed)

    # ---- modello ----------------------------------------------------------
    def _load_model(self) -> Optional[Dict[str, Any]]:
        return fetch_remote_metadata(self.client, AREAS["model"], self.sub["path"])

    def _show_model(self, meta: Optional[Dict[str, Any]]) -> None:
        self.info.setText("\n".join(model_info_lines(meta)))

    # ---- foto e dataset ---------------------------------------------------
    def _load_images(self) -> Tuple[Dict[str, Any], List[Tuple[str, Path]]]:
        area, base = AREAS[self.kind], self.sub["path"]
        info = list_preview(self.client, area, base)
        local: List[Tuple[str, Path]] = []
        for i, rel in enumerate(info["images"]):
            dest = Path(self._tmp.name) / f"{i:03d}{PurePosixPath(rel).suffix}"
            self.client.download(area, rel, dest, None, None)
            local.append((str(PurePosixPath(rel).relative_to(base)), dest))
        return info, local

    def _show_images(self, result: Tuple[Dict[str, Any], List[Tuple[str, Path]]]) -> None:
        info, local = result
        text = tr("{n} images", n=info["total"])
        if info["more"]:
            text += " - " + tr("{n} not shown", n=info["more"])
        self.info.setText(text)
        for name, path in local:
            pix = QPixmap(str(path)).scaled(THUMB, THUMB, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation)
            self.thumbs.addItem(QListWidgetItem(QIcon(pix), name))

    def _failed(self, e: Exception) -> None:
        self.info.setText(tr("Error: {msg}", msg=tr_error(e)))