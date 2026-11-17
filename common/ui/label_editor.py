"""Graphical editor of YOLO labels: correct the boxes and polygons found by the model so that the next training
learns from accurate examples. It works on photos and on single frames of a video; where the labels come from and
where they are saved is up to the caller (a local file, or the server for an administrator).

Autore: Samuele Gallo
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QPen, QPolygonF, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QHBoxLayout, QInputDialog, QLabel, QMessageBox,
                               QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget)

from common.i18n import tr
from common.label_edit import LabelModel
from common.label_shapes import Shape, class_label
from common.ui.label_style import LabelColorButton, color_for
from common.ui.layout import fit_to_screen

HANDLE_PX = 9                                   # pick distance of a handle, in screen pixels
MODE_SELECT, MODE_BOX, MODE_POLYGON = "select", "box", "polygon"
SaveCallback = Callable[[Dict[int, List[Shape]], List[str]], None]


def class_color(cls: int) -> QColor:
    """The colour of a shape: the one the user chose for contrast, or the colour of its class."""
    return color_for(cls)


# ---- where the pictures come from -------------------------------------------------------------
class FrameSource:
    """What the editor shows: one image, or the frames of a video."""
    count = 1

    def image(self, index: int) -> QImage:
        raise NotImplementedError

    def close(self) -> None:
        pass


class ImageSource(FrameSource):
    def __init__(self, image: QImage):
        if image.isNull():
            raise ValueError(tr("Could not load the image."))
        self._image = image

    def image(self, index: int = 0) -> QImage:
        return self._image


class VideoSource(FrameSource):
    def __init__(self, path: Path):
        import cv2
        self._cv2 = cv2
        self._cap = cv2.VideoCapture(str(path))
        self.count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if not self._cap.isOpened() or self.count <= 0:
            raise ValueError(tr("Could not open the video."))

    def image(self, index: int) -> QImage:
        self._cap.set(self._cv2.CAP_PROP_POS_FRAMES, max(0, min(index, self.count - 1)))
        ok, frame = self._cap.read()
        if not ok:
            return QImage()
        rgb = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()

    def close(self) -> None:
        self._cap.release()


# ---- the drawing surface -------------------------------------------------------------------------
class LabelCanvas(QWidget):
    """Shows an image with its shapes and lets the user pick, move, reshape, add and delete them."""

    edited = Signal()                                   # the shapes changed
    selected = Signal(int)                              # index of the selected shape (-1: none)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.model = LabelModel()
        self.image = QImage()
        self.names: List[str] = []
        self.mode = MODE_SELECT
        self.current_class = 0
        self.sel = -1
        self.read_only = False                         # a viewer only shows the shapes: nothing can be changed
        self.show_shapes = True                        # the "labels" button of the views turns the drawing off
        self._drag: Optional[Tuple] = None              # ("handle", si, hi) | ("shape", si, last) | ("box", start)
        self._draft: Optional[Tuple[float, float, float, float]] = None
        self._poly: List[Tuple[float, float]] = []
        self._hover: Optional[int] = None               # shape under the pointer: its points are shown
        self._new_point: Optional[Tuple[float, float]] = None   # where a point would be added, as a mark
        self.setMinimumSize(400, 300)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # -- state -----------------------------------------------------------------------------------
    def set_image(self, image: QImage) -> None:
        self.image = image
        self.update()

    def set_model(self, model: LabelModel) -> None:
        self.model = model
        self.select(-1)
        self._poly.clear()
        self.update()

    def set_shapes_visible(self, visible: bool) -> None:
        """The "labels" button of the views: draw the shapes over the media, or only the media."""
        self.show_shapes = bool(visible)
        self.update()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self._poly.clear()
        self._draft = None
        self.setCursor(Qt.CursorShape.ArrowCursor if mode == MODE_SELECT else Qt.CursorShape.CrossCursor)
        self.update()

    def select(self, si: int) -> None:
        self.sel = si
        self.selected.emit(si)
        self.update()

    # -- geometry ----------------------------------------------------------------------------------
    def _rect(self) -> QRectF:
        if self.image.isNull():
            return QRectF()
        scale = min(self.width() / self.image.width(), self.height() / self.image.height())
        w, h = self.image.width() * scale, self.image.height() * scale
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def to_norm(self, pos: QPointF) -> Tuple[float, float]:
        r = self._rect()
        if r.width() <= 0:
            return 0.0, 0.0
        return (pos.x() - r.x()) / r.width(), (pos.y() - r.y()) / r.height()

    def to_screen(self, p: Tuple[float, float]) -> QPointF:
        r = self._rect()
        return QPointF(r.x() + p[0] * r.width(), r.y() + p[1] * r.height())

    def _tol(self) -> float:
        r = self._rect()
        return HANDLE_PX / max(1.0, min(r.width(), r.height()))

    # -- painting ------------------------------------------------------------------------------------
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(30, 30, 30))
        r = self._rect()
        if r.width() <= 0:
            return
        painter.drawImage(r, self.image)
        if not self.show_shapes:                       # the labels are hidden: only the media is shown
            return painter.end()
        for i, s in enumerate(self.model.shapes):
            color = class_color(s.cls)
            painter.setPen(QPen(color, 3 if i == self.sel else 2))
            pts = [self.to_screen(p) for p in s.points]
            if s.is_box:
                rect = QRectF(pts[0], pts[1])
                painter.drawRect(rect)
                anchor = rect.topLeft()
            else:
                painter.drawPolygon(QPolygonF(pts))
                anchor = min(pts, key=lambda p: (p.y(), p.x()))
            text = class_label(self.names, s.cls)
            box = painter.fontMetrics().boundingRect(text)
            tag = QRectF(anchor.x(), max(0.0, anchor.y() - box.height() - 4), box.width() + 8, box.height() + 4)
            painter.fillRect(tag, color)
            painter.setPen(Qt.GlobalColor.black)
            painter.drawText(tag, Qt.AlignmentFlag.AlignCenter, text)
            if i == self.sel or i == self._hover:
                painter.setPen(QPen(Qt.GlobalColor.white, 1))
                painter.setBrush(color if i == self.sel else Qt.BrushStyle.NoBrush)
                size = 4.0 if i == self.sel else 3.0
                for h in self.model.handles(s):
                    c = self.to_screen(h)
                    painter.drawRect(QRectF(c.x() - size, c.y() - size, size * 2, size * 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
        if self._new_point is not None:                 # the point that a click would add, under the pointer
            c = self.to_screen(self._new_point)
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.drawLine(c.x() - 5, c.y(), c.x() + 5, c.y())
            painter.drawLine(c.x(), c.y() - 5, c.x(), c.y() + 5)
        if self._draft:
            painter.setPen(QPen(class_color(self.current_class), 2, Qt.PenStyle.DashLine))
            a, b = self.to_screen(self._draft[:2]), self.to_screen(self._draft[2:])
            painter.drawRect(QRectF(a, b))
        if self._poly:
            painter.setPen(QPen(class_color(self.current_class), 2, Qt.PenStyle.DashLine))
            pts = [self.to_screen(p) for p in self._poly]
            painter.drawPolyline(QPolygonF(pts))
            for p in pts:
                painter.drawEllipse(p, 3, 3)
        painter.end()

    # -- mouse -----------------------------------------------------------------------------------------
    def mousePressEvent(self, e) -> None:
        if self.read_only:
            return
        self.setFocus()
        x, y = self.to_norm(e.position())
        if e.button() == Qt.MouseButton.RightButton:
            return self._right_click(x, y)
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self.mode == MODE_SELECT and e.modifiers() & Qt.KeyboardModifier.AltModifier:
            return self.add_point_here(x, y)
        if self.mode == MODE_BOX:
            self._drag = ("box", (x, y))
            self._draft = (x, y, x, y)
        elif self.mode == MODE_POLYGON:
            self._add_polygon_point(x, y)
        else:
            self._press_select(x, y)
        self.update()

    def _press_select(self, x: float, y: float) -> None:
        tol = self._tol()
        hit = self.model.handle_at(x, y, tol, only=self.sel if self.sel >= 0 else None) \
            or self.model.handle_at(x, y, tol)
        if hit:
            if hit[0] != self.sel:
                self.select(hit[0])
            self.model.begin_change()
            self._drag = ("handle", hit[0], hit[1])
            return
        si = self.model.shape_at(x, y)
        if si is None:
            self.select(-1)
            return
        self.select(si)
        self.model.begin_change()
        self._drag = ("shape", si, (x, y))

    def _add_polygon_point(self, x: float, y: float) -> None:
        if len(self._poly) >= 3 and abs(x - self._poly[0][0]) <= self._tol() and abs(y - self._poly[0][1]) <= self._tol():
            return self.finish_polygon()
        self._poly.append((x, y))

    def finish_polygon(self) -> None:
        if len(self._poly) >= 3:
            self.model.begin_change()
            si = self.model.add_polygon(self.current_class, self._poly)
            if si is None:
                self.model.undo()
            else:
                self.edited.emit()
                self.select(si)
        self._poly.clear()
        self.update()

    def _right_click(self, x: float, y: float) -> None:
        """Right click on a vertex of the selected polygon removes it."""
        if self.mode != MODE_SELECT or self.sel < 0:
            return
        hit = self.model.handle_at(x, y, self._tol(), only=self.sel)
        if hit:
            self.model.begin_change()
            if self.model.remove_vertex(*hit):
                self.edited.emit()
            else:
                self.model.undo()
            self.update()

    def mouseDoubleClickEvent(self, e) -> None:
        if self.read_only:
            return
        """Double click on an edge of the selected polygon adds a vertex there."""
        if self.mode != MODE_SELECT or self.sel < 0 or e.button() != Qt.MouseButton.LeftButton:
            return
        x, y = self.to_norm(e.position())
        self.add_point_here(x, y)

    def mouseMoveEvent(self, e) -> None:
        if self.read_only:
            return
        if not self._drag:
            return self._hover_at(e.position())
        x, y = self.to_norm(e.position())
        kind = self._drag[0]
        if kind == "handle":
            self.model.move_handle(self._drag[1], self._drag[2], x, y)
        elif kind == "shape":
            _k, si, (lx, ly) = self._drag
            self.model.move_shape(si, x - lx, y - ly)
            self._drag = (kind, si, (x, y))
        elif kind == "box":
            sx, sy = self._drag[1]
            self._draft = (sx, sy, x, y)
        self.update()

    def _hover_at(self, pos) -> None:
        """Nothing is pressed: show what is under the pointer and what a click would do there."""
        if self.mode != MODE_SELECT:
            return
        x, y = self.to_norm(pos)
        tol = self._tol()
        hit = self.model.handle_at(x, y, tol)
        shape = hit[0] if hit else self.model.shape_at(x, y)
        point = None
        if hit is None and self.sel >= 0:
            point = self.model.edge_point(self.sel, x, y, tol * 1.5)     # a wider band: it is easier to catch
        cursor = Qt.CursorShape.SizeAllCursor if hit else (
            Qt.CursorShape.CrossCursor if point is not None else
            Qt.CursorShape.OpenHandCursor if shape is not None else Qt.CursorShape.ArrowCursor)
        if (shape, point, cursor) != (self._hover, self._new_point, self.cursor().shape()):
            self._hover, self._new_point = shape, point
            self.setCursor(cursor)
            self.update()

    def leaveEvent(self, event) -> None:
        self._hover, self._new_point = None, None
        self.update()
        super().leaveEvent(event)

    def add_point_here(self, x: float, y: float) -> bool:
        """Adds a point on the edge of the selected polygon (double click, or Alt and a click)."""
        if self.sel < 0:
            return False
        self.model.begin_change()
        if self.model.insert_vertex(self.sel, x, y, self._tol() * 1.5) is None:
            self.model.undo()
            return False
        self.edited.emit()
        self._new_point = None
        self.update()
        return True

    def subdivide_selected(self) -> int:
        """Doubles the points of the selected polygon without changing its shape: more nodes to work with."""
        if self.sel < 0:
            return 0
        self.model.begin_change()
        added = self.model.subdivide(self.sel)
        if not added:
            self.model.undo()
        else:
            self.edited.emit()
        self.update()
        return added

    def to_polygon_selected(self) -> bool:
        """A box becomes a polygon of four points, so it can be shaped point by point as well."""
        if self.sel < 0:
            return False
        self.model.begin_change()
        if not self.model.to_polygon(self.sel):
            self.model.undo()
            return False
        self.edited.emit()
        self.update()
        return True

    def mouseReleaseEvent(self, e) -> None:
        if self.read_only:
            return
        if not self._drag:
            return
        kind = self._drag[0]
        if kind == "box" and self._draft:
            a, b, c, d = self._draft
            self.model.begin_change()
            si = self.model.add_box(self.current_class, a, b, c, d)
            if si is None:
                self.model.undo()                         # too small: it was only a click
            else:
                self.edited.emit()
                self.select(si)
        elif kind in ("handle", "shape"):
            self.edited.emit()
        self._drag, self._draft = None, None
        self.update()

    # -- keyboard --------------------------------------------------------------------------------------
    def keyPressEvent(self, e) -> None:
        if self.read_only:
            return
        key = e.key()
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
        elif key == Qt.Key.Key_Escape:
            self._poly.clear()
            self._draft = None
            self.update()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.mode == MODE_POLYGON:
            self.finish_polygon()
        else:
            super().keyPressEvent(e)

    def delete_selected(self) -> None:
        if 0 <= self.sel < len(self.model.shapes):
            self.model.begin_change()
            self.model.delete(self.sel)
            self.select(-1)
            self.edited.emit()

    def set_class_of_selected(self, cls: int) -> None:
        if 0 <= self.sel < len(self.model.shapes) and self.model.shapes[self.sel].cls != cls:
            self.model.begin_change()
            self.model.set_class(self.sel, cls)
            self.edited.emit()
            self.update()


# ---- the window --------------------------------------------------------------------------------------------
class LabelEditorDialog(QDialog):
    """`frames`: what to show; `labels`: the shapes of each frame ({0: [...]} for a photo); `classes`: the class
    names (a class may be added while editing); `on_save(labels, classes)` stores the result."""

    def __init__(self, frames: FrameSource, labels: Dict[int, Sequence[Shape]], classes: Sequence[str],
                 on_save: SaveCallback, title: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.frames, self.on_save = frames, on_save
        self.classes: List[str] = list(classes)
        self.models: Dict[int, LabelModel] = {f: LabelModel(s) for f, s in labels.items()}
        self.frame = min(labels) if labels and frames.count > 1 else 0
        self.creating = not any(shapes for shapes in labels.values())   # nothing yet: this is a first drawing
        what = tr("Create labels") if self.creating else tr("Edit labels")
        self.setWindowTitle(f"{what} - {title}" if title else what)
        fit_to_screen(self, 1000, 700)
        lay = QVBoxLayout(self)

        bar = QHBoxLayout()
        self.group = QButtonGroup(self)
        self.btn_select = self._tool(tr("Select"), MODE_SELECT, bar)
        self.btn_box = self._tool(tr("Draw box"), MODE_BOX, bar)
        self.btn_polygon = self._tool(tr("Draw polygon"), MODE_POLYGON, bar)
        self.btn_select.setChecked(True)
        self.btn_delete = QPushButton(tr("Delete"))
        self.btn_undo = QPushButton(tr("Undo"))
        self.btn_redo = QPushButton(tr("Redo"))
        for b in (self.btn_delete, self.btn_undo, self.btn_redo):
            bar.addWidget(b)
        bar.addSpacing(12)
        self.btn_more_points = QPushButton(tr("More points"))
        self.btn_more_points.setToolTip(tr("Adds a point in the middle of every edge of the chosen shape."))
        bar.addWidget(self.btn_more_points)
        self.btn_to_polygon = QPushButton(tr("Box to polygon"))
        self.btn_to_polygon.setToolTip(tr("Turns the chosen box into a polygon that can be shaped point by point."))
        bar.addWidget(self.btn_to_polygon)
        self.btn_color = LabelColorButton()
        bar.addWidget(self.btn_color)
        bar.addSpacing(12)
        bar.addWidget(QLabel(tr("Class")))
        self.combo = QComboBox()
        bar.addWidget(self.combo)
        self.btn_new_class = QPushButton(tr("New class..."))
        bar.addWidget(self.btn_new_class)
        bar.addStretch(1)
        lay.addLayout(bar)

        self.canvas = LabelCanvas()
        lay.addWidget(self.canvas, 1)

        self.nav = QWidget()
        nav = QHBoxLayout(self.nav)
        nav.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, max(0, frames.count - 1))
        self.spin = QSpinBox()
        self.spin.setRange(0, max(0, frames.count - 1))
        self.btn_prev_label = QPushButton(tr("Previous labelled frame"))
        self.btn_next_label = QPushButton(tr("Next labelled frame"))
        nav.addWidget(self.btn_prev_label)
        nav.addWidget(self.slider, 1)
        nav.addWidget(self.spin)
        nav.addWidget(self.btn_next_label)
        self.nav.setVisible(frames.count > 1)
        lay.addWidget(self.nav)

        self.status = QLabel("")
        lay.addWidget(self.status)
        row = QHBoxLayout()
        self.hint = QLabel(tr("Drag a corner or a point to correct it, drag inside to move. Double click (or Alt and "
                              "click) on an edge to add a point, right click a point to remove it, 'More points' "
                              "to add one on every edge."))
        self.hint.setWordWrap(True)
        row.addWidget(self.hint, 1)
        self.btn_save = QPushButton(tr("Save"))
        self.btn_close = QPushButton(tr("Close"))
        row.addWidget(self.btn_save)
        row.addWidget(self.btn_close)
        lay.addLayout(row)

        self.canvas.edited.connect(self._edited)
        self.canvas.selected.connect(self._selected)
        self.group.idToggled.connect(lambda *_: None)
        self.btn_delete.clicked.connect(self.canvas.delete_selected)
        self.btn_more_points.clicked.connect(self._more_points)
        self.btn_to_polygon.clicked.connect(self._to_polygon)
        self.btn_color.changed.connect(self.canvas.update)
        self.btn_undo.clicked.connect(lambda: self._history(True))
        self.btn_redo.clicked.connect(lambda: self._history(False))
        self.combo.currentIndexChanged.connect(self._class_chosen)
        self.btn_new_class.clicked.connect(self._new_class)
        self.slider.valueChanged.connect(self.goto)
        self.spin.valueChanged.connect(self.goto)
        self.btn_prev_label.clicked.connect(lambda: self._jump(-1))
        self.btn_next_label.clicked.connect(lambda: self._jump(1))
        self.btn_save.clicked.connect(self.save)
        self.btn_close.clicked.connect(self.close)
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=lambda: self._history(True))
        QShortcut(QKeySequence.StandardKey.Redo, self, activated=lambda: self._history(False))
        QShortcut(QKeySequence.StandardKey.Save, self, activated=self.save)
        self._fill_classes()
        self.goto(self.frame)
        self._selected(self.canvas.sel)              # nothing chosen yet: the buttons that need a shape are off
        if self.creating:                            # first labels of this file: start with a tool in hand
            self.btn_box.setChecked(True)
            self.canvas.set_mode(MODE_BOX)

    def _tool(self, text: str, mode: str, bar: QHBoxLayout) -> QPushButton:
        b = QPushButton(text)
        b.setCheckable(True)
        b.clicked.connect(lambda: self.canvas.set_mode(mode))
        self.group.addButton(b)
        bar.addWidget(b)
        return b

    # -- classes ---------------------------------------------------------------------------------------
    def _fill_classes(self) -> None:
        keep = self.combo.currentIndex()
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItems(self.classes or ["0"])
        self.combo.setCurrentIndex(max(0, min(keep, self.combo.count() - 1)))
        self.combo.blockSignals(False)
        self.canvas.names = self.classes
        self.canvas.current_class = self.combo.currentIndex()
        self.canvas.update()

    def _class_chosen(self, index: int) -> None:
        """The chosen class is used for new shapes and, if a shape is selected, replaces its class."""
        self.canvas.current_class = max(0, index)
        self.canvas.set_class_of_selected(max(0, index))

    def _more_points(self) -> None:
        if not self.canvas.subdivide_selected():
            self.status.setText(tr("Choose a polygon first ('Box to polygon' turns a box into one)."))

    def _to_polygon(self) -> None:
        if not self.canvas.to_polygon_selected():
            self.status.setText(tr("Choose a box to turn into a polygon."))

    def _selected(self, si: int) -> None:
        shapes = self.canvas.model.shapes
        chosen = 0 <= si < len(shapes)
        self.btn_more_points.setEnabled(chosen and not shapes[si].is_box)
        self.btn_to_polygon.setEnabled(chosen and shapes[si].is_box)
        if 0 <= si < len(self.canvas.model.shapes):
            cls = self.canvas.model.shapes[si].cls
            if cls < self.combo.count():
                self.combo.blockSignals(True)
                self.combo.setCurrentIndex(cls)
                self.combo.blockSignals(False)
                self.canvas.current_class = cls
        self._refresh()

    def _new_class(self) -> None:
        name, ok = QInputDialog.getText(self, tr("New class..."), tr("Class name"))
        name = name.strip()
        if ok and name and name not in self.classes:
            self.classes.append(name)
            self._fill_classes()
            self.combo.setCurrentIndex(len(self.classes) - 1)

    # -- frames ------------------------------------------------------------------------------------------
    def _model(self, frame: int) -> LabelModel:
        return self.models.setdefault(frame, LabelModel())

    def goto(self, frame: int) -> None:
        frame = max(0, min(frame, self.frames.count - 1))
        for w in (self.slider, self.spin):
            w.blockSignals(True)
            w.setValue(frame)
            w.blockSignals(False)
        self.frame = frame
        self.canvas.set_image(self.frames.image(frame))
        self.canvas.set_model(self._model(frame))
        self._fill_classes()
        self._refresh()

    def _jump(self, step: int) -> None:
        labelled = sorted(f for f, m in self.models.items() if m.shapes and f != self.frame)
        target = [f for f in labelled if (f > self.frame if step > 0 else f < self.frame)]
        if target:
            self.goto(min(target) if step > 0 else max(target))

    # -- editing -------------------------------------------------------------------------------------------
    def _history(self, undo: bool) -> None:
        if (self.canvas.model.undo() if undo else self.canvas.model.redo()):
            self.canvas.select(-1)
            self._edited()

    def _edited(self) -> None:
        self.canvas.update()
        self._refresh()

    def _refresh(self) -> None:
        n = len(self.canvas.model.shapes)
        where = tr("Frame {n}", n=self.frame) + " - " if self.frames.count > 1 else ""
        self.status.setText(where + tr("{n} labelled objects", n=n) + (" *" if self.dirty else ""))

    @property
    def dirty(self) -> bool:
        return any(m.dirty for m in self.models.values())

    def result(self) -> Dict[int, List[Shape]]:
        return {f: list(m.shapes) for f, m in self.models.items() if m.shapes}

    def save(self) -> bool:
        try:
            self.on_save(self.result(), self.classes)
        except Exception as e:                                         # noqa: BLE001 - shown to the user
            QMessageBox.warning(self, tr("Error"), str(e))
            return False
        for m in self.models.values():
            m.mark_saved()
        self._refresh()
        return True

    def closeEvent(self, event) -> None:
        if self.dirty:
            box = QMessageBox(self)
            box.setWindowTitle(tr("Create labels") if self.creating else tr("Edit labels"))
            box.setText(tr("Save the changes to the labels?"))
            save = box.addButton(tr("Save"), QMessageBox.ButtonRole.AcceptRole)
            box.addButton(tr("Discard"), QMessageBox.ButtonRole.DestructiveRole)
            cancel = box.addButton(tr("Cancel"), QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is cancel or (box.clickedButton() is save and not self.save()):
                return event.ignore()
        self.frames.close()
        super().closeEvent(event)


# ---- editing the labels of a file on this computer --------------------------------------------------
def edit_local_labels(parent: Optional[QWidget], media: Path) -> None:
    """Opens the editor on a photo or video of this computer. The labels it finds (next to the file, or saved by the
    analysis) are corrected and saved where they came from, so the upload sends the corrected ones."""
    from common.label_shapes import format_labels, format_video_labels, parse_labels, parse_video_labels
    from common.label_store import read_labels, write_labels
    from common.params import VIDEO_SUFFIXES

    media = Path(media)
    is_video = media.suffix.lower() in VIDEO_SUFFIXES
    text, classes, beside = read_labels(media)
    try:
        if is_video:
            source: FrameSource = VideoSource(media)
            labels = parse_video_labels(text)
        else:
            source = ImageSource(QImage(str(media)))
            labels = {0: parse_labels(text)}
    except ValueError as e:
        QMessageBox.warning(parent, tr("Error"), str(e))
        return

    def save(result: Dict[int, List[Shape]], names: List[str]) -> None:
        body = format_video_labels(result) if is_video else format_labels(result.get(0, []))
        write_labels(media, body, names, beside)

    LabelEditorDialog(source, labels, classes, save, media.name, parent).exec()
