"""Looking at a photo or a video of this computer with the labels on top of it.

Every view of the files (local folders, server) opens this: the media fills the window, a button shows or hides
the labels the analysis produced, another one opens the editor for correcting them by hand, and the improvement of
the image is asked from here as well (on this computer or on the server).

When an improved copy of the file exists, a switch shows it in place of the original: it is the same picture seen
in another way, so the labels stay drawn on top of either.

Autore: Samuele Gallo
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSlider,
                               QVBoxLayout, QWidget)

from common.i18n import tr
from common.image_enhance import find_enhanced
from common.label_edit import LabelModel
from common.label_shapes import Shape, parse_labels, parse_video_labels
from common.label_store import read_labels
from common.params import VIDEO_SUFFIXES
from common.ui.label_editor import FrameSource, ImageSource, LabelCanvas, VideoSource, edit_local_labels
from common.ui.label_style import LabelColorButton, labels_visible, set_labels_visible


def is_video(media: Path) -> bool:
    return Path(media).suffix.lower() in tuple(VIDEO_SUFFIXES)


def labels_of(media: Path) -> Dict[int, List[Shape]]:
    """The shapes of a file, by frame (a photo has only frame 0). Empty when it has never been analysed."""
    text, _classes, _beside = read_labels(media)
    if not text.strip():
        return {}
    return parse_video_labels(text) if is_video(media) else {0: parse_labels(text)}


def class_names(media: Path) -> List[str]:
    return read_labels(media)[1]


class MediaViewerDialog(QDialog):
    """One photo or video, with its labels on top and what can be done with them."""

    def __init__(self, media: Path, parent: Optional[QWidget] = None, show_labels: Optional[bool] = None,
                 improve: Optional[Callable[[Path], None]] = None):
        super().__init__(parent)
        show_labels = labels_visible() if show_labels is None else show_labels
        self.media = Path(media)
        self.shown = self.media                              # the original, or its improved copy
        self.improve = improve
        self.setWindowTitle(self.media.name)
        self.resize(900, 640)
        lay = QVBoxLayout(self)

        self.canvas = LabelCanvas(self)
        self.canvas.read_only = True
        self.canvas.set_shapes_visible(show_labels)
        lay.addWidget(self.canvas, 1)

        self.frames: Optional[FrameSource] = None
        self.frame = 0
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.valueChanged.connect(self.goto)
        lay.addWidget(self.slider)

        row = QHBoxLayout()
        self.improved = QCheckBox(tr("Improved"))            # only when an improved copy has been made
        self.improved.setToolTip(tr("Shows the improved copy in place of the original."))
        self.improved.toggled.connect(self._show_improved)
        row.addWidget(self.improved)
        self.toggle = QCheckBox(tr("Show labels"))
        self.toggle.setChecked(show_labels)
        self.toggle.toggled.connect(self.canvas.set_shapes_visible)
        self.toggle.toggled.connect(set_labels_visible)          # the choice holds for the previews as well
        row.addWidget(self.toggle)
        self.colour = LabelColorButton()                         # better contrast while looking or correcting
        self.colour.changed.connect(self.canvas.update)
        row.addWidget(self.colour)
        self.count = QLabel("")
        row.addWidget(self.count)
        row.addStretch(1)
        self.btn_edit = QPushButton(tr("Edit labels..."))        # becomes "Create" when the file has none
        self.btn_edit.clicked.connect(self._edit)
        row.addWidget(self.btn_edit)
        if improve is not None:
            self.btn_improve = QPushButton(tr("Improve..."))
            self.btn_improve.clicked.connect(lambda: improve(self.media))
            row.addWidget(self.btn_improve)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        self.reload()

    # ---- content -------------------------------------------------------
    def reload(self) -> None:
        """Reads the media and its labels again (after an edit, or when the file has been replaced)."""
        self._close_frames()
        better = find_enhanced(self.media)
        self.improved.setVisible(better is not None)
        if better is None:
            self.improved.setChecked(False)
        self.shown = better if (better is not None and self.improved.isChecked()) else self.media
        try:
            self.frames = VideoSource(self.shown) if is_video(self.shown) else ImageSource(QImage(str(self.shown)))
        except ValueError as e:
            QMessageBox.warning(self, tr("Error"), str(e))
            self.reject()
            return
        self.shapes = labels_of(self.media)
        self.canvas.names = class_names(self.media)
        total = max(1, int(getattr(self.frames, "count", 1)))
        self.slider.setVisible(total > 1)
        self.slider.setRange(0, total - 1)
        self.goto(min(self.frame, total - 1))

    def goto(self, index: int) -> None:
        if self.frames is None:
            return
        self.frame = max(0, index)
        self.canvas.set_image(self.frames.image(self.frame))
        shapes: Sequence[Shape] = self.shapes.get(self.frame, ())
        self.canvas.set_model(LabelModel(shapes))
        self.count.setText(tr("{n} labels", n=len(shapes)) if self.shapes else tr("No label"))
        self.btn_edit.setText(tr("Edit labels...") if self.shapes else tr("Create labels..."))

    def _show_improved(self, _on: bool) -> None:
        """The same labels, drawn over the other picture: nothing is changed on disk."""
        self.reload()

    def _edit(self) -> None:
        edit_local_labels(self, self.media)
        self.reload()

    # ---- closing -------------------------------------------------------
    def _close_frames(self) -> None:
        if self.frames is not None:
            self.frames.close()
            self.frames = None

    def closeEvent(self, event) -> None:
        self._close_frames()
        super().closeEvent(event)


def view_media(parent: Optional[QWidget], media: Path, show_labels: Optional[bool] = None,
               improve: Optional[Callable[[Path], None]] = None) -> None:
    """Opens the viewer on a file of this computer."""
    MediaViewerDialog(Path(media), parent, show_labels, improve).exec()
