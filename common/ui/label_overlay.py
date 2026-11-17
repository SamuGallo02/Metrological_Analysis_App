"""Drawing the labels on top of a picture: the previews, the viewers and the server showcase all use this one.

The colour is the one the user chose for contrast (`common.ui.label_style`); on a small preview only the outline
is drawn, because a class name would cover the picture itself.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPen, QPolygonF

from common.label_shapes import Shape, class_label, parse_labels, parse_video_labels
from common.label_store import read_labels
from common.params import VIDEO_SUFFIXES
from common.ui.label_style import color_for


def draw_shapes(image: QImage, shapes: Sequence[Shape], names: Optional[List[str]] = None,
                with_names: bool = True) -> QImage:
    """A copy of `image` with the boxes and the polygons (and, if there is room, the class names) drawn on it."""
    if image.isNull() or not shapes:
        return image
    out = image.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = out.width(), out.height()
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    width = max(1.0, min(w, h) / 200)
    font = painter.font()
    font.setPixelSize(max(12, int(min(w, h) / 35)))
    painter.setFont(font)
    for s in shapes:
        color = color_for(s.cls)
        painter.setPen(QPen(color, width))
        pts = [QPointF(x * w, y * h) for x, y in s.points]
        if s.is_box:
            rect = QRectF(pts[0], pts[1])
            painter.drawRect(rect)
            anchor = rect.topLeft()
        else:
            painter.drawPolygon(QPolygonF(pts))
            anchor = min(pts, key=lambda p: (p.y(), p.x()))
        if not with_names:
            continue
        text = class_label(names, s.cls)
        box = painter.fontMetrics().boundingRect(text)
        tag = QRectF(anchor.x(), max(0.0, anchor.y() - box.height() - 4), box.width() + 8, box.height() + 4)
        painter.fillRect(tag, color)
        painter.setPen(Qt.GlobalColor.black)
        painter.drawText(tag, Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return out


def shapes_of(media: Path, frame: int = 0) -> List[Shape]:
    """The labels of a file of this computer, if it has any (a video: those of one frame)."""
    media = Path(media)
    text, _names, _beside = read_labels(media)
    if not text.strip():
        return []
    if media.suffix.lower() in tuple(VIDEO_SUFFIXES):
        return list(parse_video_labels(text).get(frame, []))
    return list(parse_labels(text))


def names_of(media: Path) -> List[str]:
    return read_labels(Path(media))[1]


def with_labels(image: QImage, media: Path, with_names: bool = False) -> QImage:
    """The preview of a local file with its labels on top, when it has them. Used by the small previews, where
    the names are left out: at that size they would hide the picture."""
    shapes = shapes_of(media)
    if not shapes:
        return image
    return draw_shapes(image, shapes, names_of(media) if with_names else None, with_names)
