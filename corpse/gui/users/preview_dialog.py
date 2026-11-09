"""Anteprima di un invio nella Revisione: miniature per foto e dataset, dettagli per un modello."""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QListView, QListWidget, QListWidgetItem,
                               QVBoxLayout, QWidget)

from common.i18n import tr, tr_error
from common.model_metadata import fetch_remote_metadata
from common.params import KIND_AREA, KINDS_VIDEO, VIDEO_SUFFIXES
from common.remote_tree import walk_remote
from common.ui.qt_utils import run_async
from corpse.functions.users.preview import list_preview
from .model_info import model_info_lines

THUMB = 140
AREAS = KIND_AREA                                              # kind of submission -> server area


class PreviewDialog(QDialog):
    """`sub` è una riga di invio (serve il suo `path`, relativo all'area del suo tipo)."""

    def __init__(self, client: Any, kind: str, sub: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.client, self.kind, self.sub = client, kind, sub
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
        self.thumbs.setHidden(kind == "model" or kind in KINDS_VIDEO)     # models and videos have no thumbnails
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay.addWidget(self.info)
        lay.addWidget(self.thumbs, 1)
        lay.addWidget(buttons)
        if kind == "model":
            run_async(self, self._load_model, self._show_model, self._failed)
        elif kind in KINDS_VIDEO:
            run_async(self, self._load_videos, self._show_videos, self._failed)
        else:
            run_async(self, self._load_images, self._show_images, self._failed)

    # ---- modello ----------------------------------------------------------
    def _load_model(self) -> Optional[Dict[str, Any]]:
        return fetch_remote_metadata(self.client, AREAS["model"], self.sub["path"])

    def _show_model(self, meta: Optional[Dict[str, Any]]) -> None:
        self.info.setText("\n".join(model_info_lines(meta)))

    # ---- videos -----------------------------------------------------------
    def _load_videos(self) -> List[Tuple[str, int]]:
        base = self.sub["path"]
        return [(str(PurePosixPath(rel).relative_to(base)), size)
                for rel, size in walk_remote(self.client, AREAS[self.kind], base)
                if PurePosixPath(rel).suffix.lower() in VIDEO_SUFFIXES]

    def _show_videos(self, videos: List[Tuple[str, int]]) -> None:
        lines = [tr("{n} videos", n=len(videos))] + [f"{name} ({size >> 20} MB)" for name, size in videos[:30]]
        self.info.setText("\n".join(lines))

    # ---- photos, stereo photos and datasets -------------------------------
    def _load_images(self) -> Tuple[Dict[str, Any], List[Tuple[str, QImage]]]:
        """Thumbnails are built from bytes held in memory: no file is written on this computer."""
        area, base = AREAS[self.kind], self.sub["path"]
        info = list_preview(self.client, area, base)
        thumbs: List[Tuple[str, QImage]] = []
        for rel in info["images"]:
            try:
                img = QImage.fromData(self.client.read_bytes(area, rel))
            except Exception:                                    # an unreadable image must not block the others
                continue
            if not img.isNull():
                thumbs.append((str(PurePosixPath(rel).relative_to(base)),
                               img.scaled(THUMB, THUMB, Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)))
        return info, thumbs

    def _show_images(self, result: Tuple[Dict[str, Any], List[Tuple[str, QImage]]]) -> None:
        info, thumbs = result
        text = tr("{n} images", n=info["total"])
        if info["more"]:
            text += " - " + tr("{n} not shown", n=info["more"])
        self.info.setText(text)
        for name, img in thumbs:                                 # QImage is thread-safe; QPixmap only on the GUI thread
            self.thumbs.addItem(QListWidgetItem(QIcon(QPixmap.fromImage(img)), name))

    def _failed(self, e: Exception) -> None:
        self.info.setText(tr("Error: {msg}", msg=tr_error(e)))