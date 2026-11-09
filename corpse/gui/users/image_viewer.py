"""Opens a photo of the server catalog; if it has YOLO labels, the same photo with the labels drawn is shown on its right."""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
                               QWidget)

from common.i18n import tr, tr_error
from common.label_shapes import format_labels
from common.remote_tree import walk_remote
from common.ui.label_editor import ImageSource, LabelEditorDialog
from common.ui.qt_utils import run_async
from corpse.functions.users.yolo_labels import (Shape, class_label, class_names, label_candidates, names_candidates,
                                                parse_labels)


def label_color(cls: int) -> QColor:
    """A distinct, stable colour for each class."""
    return QColor.fromHsv((cls * 67) % 360, 220, 255)


def draw_labels(image: QImage, shapes: List[Shape], names: Optional[List[str]] = None) -> QImage:
    """A copy of `image` with the boxes / polygons (and class names) drawn on it."""
    out = image.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = out.width(), out.height()
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    width = max(2.0, min(w, h) / 200)
    font = painter.font()
    font.setPixelSize(max(12, int(min(w, h) / 35)))
    painter.setFont(font)
    for s in shapes:
        color = label_color(s.cls)
        painter.setPen(QPen(color, width))
        pts = [QPointF(x * w, y * h) for x, y in s.points]
        if s.is_box:
            rect = QRectF(pts[0], pts[1])
            painter.drawRect(rect)
            anchor = rect.topLeft()
        else:
            painter.drawPolygon(QPolygonF(pts))
            anchor = min(pts, key=lambda p: (p.y(), p.x()))
        text = class_label(names, s.cls)
        box = painter.fontMetrics().boundingRect(text)
        tag = QRectF(anchor.x(), max(0.0, anchor.y() - box.height() - 4), box.width() + 8, box.height() + 4)
        painter.fillRect(tag, color)
        painter.setPen(Qt.GlobalColor.black)
        painter.drawText(tag, Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return out


class _Pane(QLabel):
    """Shows a pixmap scaled to the available room, whatever the window size."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._pix: Optional[QPixmap] = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(200, 150)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

    def set_image(self, image: QImage) -> None:
        self._pix = QPixmap.fromImage(image)
        self._fit()

    def _fit(self) -> None:
        if self._pix is not None:
            self.setPixmap(self._pix.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._fit()


class ImageViewerDialog(QDialog):
    """`rel` is the path of the photo in `area` of the server. Everything is read into memory (nothing is saved)."""

    def __init__(self, client: Any, area: str, rel: str, parent: Optional[QWidget] = None,
                 labels_area: Optional[str] = None, editable: bool = False):
        """`labels_area`: another area of the server (the datasets) where the labels of this photo may be kept:
        it is searched, under the same species folder, for a label file with the same name as the photo."""
        super().__init__(parent)
        self.client, self.area, self.rel, self.labels_area = client, area, rel, labels_area
        self.editable = editable                                  # administrators can correct the labels
        self.shapes: List[Shape] = []
        self.names: List[str] = []
        self.original: Optional[QImage] = None
        self.labelled: Optional[QImage] = None
        self.setWindowTitle(rel)
        self.resize(1000, 560)
        lay = QVBoxLayout(self)
        self.note = QLabel(tr("Loading..."))
        self.note.setTextFormat(Qt.TextFormat.PlainText)
        lay.addWidget(self.note)
        row = QHBoxLayout()
        self.left, self.right = _Pane(), _Pane()
        self.right.setVisible(False)                             # only when the photo has labels
        row.addWidget(self.left, 1)
        row.addWidget(self.right, 1)
        lay.addLayout(row, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        self.btn_edit = QPushButton(tr("Edit labels..."))
        self.btn_edit.setVisible(editable)
        self.btn_edit.setEnabled(False)                          # until the photo is loaded
        self.btn_edit.clicked.connect(self._edit)
        buttons.addButton(self.btn_edit, QDialogButtonBox.ButtonRole.ActionRole)
        lay.addWidget(buttons)
        run_async(self, self._load, self._show, lambda e: self.note.setText(tr("Error: {msg}", msg=tr_error(e))))

    def _read_text(self, rel: str, area: Optional[str] = None) -> Optional[str]:
        try:
            return self.client.read_bytes(area or self.area, rel, 1 << 20).decode("utf-8")
        except Exception:                                        # noqa: BLE001 - a missing file just means "no labels"
            return None

    def _load(self) -> Tuple[QImage, List[Shape], List[str]]:
        image = QImage.fromData(self.client.read_bytes(self.area, self.rel))
        if image.isNull():
            raise ValueError(tr("Could not load the image."))
        shapes: List[Shape] = []
        for cand in label_candidates(self.rel):
            text = self._read_text(cand)
            if text is not None:
                shapes = parse_labels(text)
                break
        found_area, found = self.area, self.rel
        if not shapes and self.labels_area:
            found_area, found, shapes = self._labels_elsewhere()
        names: List[str] = []
        if shapes:
            for cand in names_candidates(found):
                text = self._read_text(cand, found_area)
                if text is not None:
                    names = class_names(cand, text)
                    if names:
                        break
        return image, shapes, names

    def _labels_elsewhere(self) -> Tuple[str, str, List[Shape]]:
        """Looks for `<photo name>.txt` in a `labels` folder under the same species folder of `labels_area`."""
        species = PurePosixPath(self.rel).parts[0]
        wanted = PurePosixPath(self.rel).with_suffix(".txt").name
        try:
            for rel, _size in walk_remote(self.client, self.labels_area, species):
                p = PurePosixPath(rel)
                if p.name == wanted and p.parent.name.lower() == "labels":
                    text = self._read_text(rel, self.labels_area)
                    if text is not None:
                        return self.labels_area, rel, parse_labels(text)
        except Exception:                                        # noqa: BLE001 - no such folder: no labels
            pass
        return self.area, self.rel, []

    def _show(self, result: Tuple[QImage, List[Shape], List[str]]) -> None:
        image, shapes, names = result
        self.original = image
        self.shapes, self.names = shapes, names
        self.btn_edit.setEnabled(True)
        self.left.set_image(image)
        if shapes:
            self.labelled = draw_labels(image, shapes, names)
            self.right.set_image(self.labelled)
            self.right.setVisible(True)
            self.note.setText(tr("{n} labelled objects", n=len(shapes)))
        else:
            self.labelled = None
            self.right.setVisible(False)
            self.note.setText(tr("No labels found for this photo."))

    def _edit(self) -> None:
        """Opens the label editor; what is saved replaces the labels of this photo on the server."""
        if self.original is None:
            return

        def save(result, classes) -> None:
            self.client.save_labels(self.area, self.rel, format_labels(result.get(0, [])),
                                    "".join(c + "\n" for c in classes))

        dialog = LabelEditorDialog(ImageSource(self.original), {0: self.shapes}, self.names, save, self.rel, self)
        dialog.exec()
        self.note.setText(tr("Loading..."))                     # shows the saved labels
        run_async(self, self._load, self._show, lambda e: self.note.setText(tr("Error: {msg}", msg=tr_error(e))))
