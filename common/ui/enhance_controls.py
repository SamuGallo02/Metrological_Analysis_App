"""The two pieces of interface the improvement needs: its settings, and the before/after view.

Neither of them knows the algorithms. The settings are built from what the method says about itself
(`common.image_enhance.Method.params`), so a new model brings its own controls with it; the view simply shows two
images with a divider the user drags to compare them.

Autore: Samuele Gallo
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QSlider, QVBoxLayout,
                               QWidget)

from common.i18n import tr

STEPS = 100                                              # how finely a slider cuts a range of numbers


class ParamControls(QWidget):
    """A control for every setting of a method: a tick for yes/no, a slider for numbers, a list for choices."""

    changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.form = QFormLayout(self)
        self.form.setContentsMargins(0, 0, 0, 0)
        self._readers: Dict[str, Any] = {}

    def set_params(self, params: Sequence[Dict[str, Any]]) -> None:
        """Builds the controls again for another method."""
        while self.form.count():
            item = self.form.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._readers = {}
        for p in params or ():
            name, label = p.get("name", ""), p.get("label") or p.get("name", "")
            if not name:
                continue
            widget, read = self._control(p)
            if p.get("help"):
                widget.setToolTip(p["help"])
            self._readers[name] = read
            self.form.addRow(label, widget)
        self.setVisible(bool(self._readers))

    def values(self) -> Dict[str, Any]:
        return {name: read() for name, read in self._readers.items()}

    # ---- one control ---------------------------------------------------
    def _control(self, p: Dict[str, Any]):
        kind = p.get("type", "float")
        if kind == "bool":
            box = QCheckBox()
            box.setChecked(bool(p.get("default")))
            box.toggled.connect(self.changed)
            return box, box.isChecked
        if kind == "choice":
            combo = QComboBox()
            choices = [str(c) for c in (p.get("choices") or [])]
            combo.addItems(choices)
            if p.get("default") in choices:
                combo.setCurrentText(str(p["default"]))
            combo.currentTextChanged.connect(self.changed)
            return combo, combo.currentText
        return self._number(p, whole=kind == "int")

    def _number(self, p: Dict[str, Any], whole: bool):
        low = float(p.get("min", 0.0))
        high = float(p.get("max", max(1.0, low + 1.0)))
        default = float(p.get("default", low))
        step = float(p.get("step") or (1.0 if whole else (high - low) / STEPS or 0.01))
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        slider = QSlider(Qt.Orientation.Horizontal)
        ticks = max(1, round((high - low) / step))
        slider.setRange(0, ticks)
        slider.setValue(round((default - low) / step))
        shown = QLabel()
        shown.setMinimumWidth(44)
        lay.addWidget(slider, 1)
        lay.addWidget(shown)

        def value():
            raw = low + slider.value() * step
            return int(round(raw)) if whole else round(raw, 3)

        def refresh():
            shown.setText(str(value()))
            self.changed.emit()

        slider.valueChanged.connect(refresh)
        shown.setText(str(value()))
        return row, value


class BeforeAfter(QWidget):
    """The original and the improved picture, one over the other, with a divider dragged by hand."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.before: Optional[QImage] = None
        self.after: Optional[QImage] = None
        self.split = 0.5                                 # where the divider is, from 0 (all improved) to 1
        self.setMinimumHeight(220)
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    def set_images(self, before: Optional[QImage], after: Optional[QImage]) -> None:
        self.before, self.after = before, after
        self.update()

    def clear(self) -> None:
        self.set_images(None, None)

    # ---- the divider follows the mouse ---------------------------------
    def mousePressEvent(self, event) -> None:
        self._move_to(event.position().toPoint())

    def mouseMoveEvent(self, event) -> None:
        self._move_to(event.position().toPoint())

    def _move_to(self, point: QPoint) -> None:
        if self.width():
            self.split = min(1.0, max(0.0, point.x() / self.width()))
            self.update()

    # ---- drawing -------------------------------------------------------
    def _area(self, image: QImage) -> QRect:
        """The picture, as large as it fits, in the middle."""
        size = image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRect(QPoint((self.width() - size.width()) // 2, (self.height() - size.height()) // 2), size)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(30, 30, 30))
        if self.before is None and self.after is None:
            painter.setPen(QColor(200, 200, 200))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("The preview appears here."))
            return
        shown = self.before if self.before is not None else self.after
        area = self._area(shown)
        if self.after is not None:
            painter.drawImage(area, self.after)
        if self.before is not None:
            cut = int(area.width() * self.split)
            painter.drawImage(QRect(area.x(), area.y(), cut, area.height()), self.before,
                              QRect(0, 0, int(self.before.width() * self.split), self.before.height()))
            line = area.x() + cut
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.drawLine(line, area.y(), line, area.bottom())
        self._captions(painter, area)

    def _captions(self, painter: QPainter, area: QRect) -> None:
        font = QFont(painter.font())
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        if self.before is not None:
            painter.drawText(area.adjusted(8, 6, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                             tr("Original"))
        if self.after is not None:
            painter.drawText(area.adjusted(0, 6, -8, 0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                             tr("Improved"))


def image_of(pixmap: QPixmap) -> QImage:
    return pixmap.toImage() if isinstance(pixmap, QPixmap) else pixmap
