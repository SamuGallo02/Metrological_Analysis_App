"""The editing logic of the label editor, without any user interface: which handle or shape is under a point,
moving, resizing, adding and deleting shapes, changing classes, undo and redo. Coordinates are normalised (0..1)."""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from .label_shapes import Shape, format_labels

Point = Tuple[float, float]
MIN_SIDE = 0.002                     # a box thinner than this (fraction of the image) is dropped


def _clamp(v: float) -> float:
    return min(1.0, max(0.0, v))


def _inside(poly: Sequence[Point], x: float, y: float) -> bool:
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        (xi, yi), (xj, yj) = poly[i], poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def _area(poly: Sequence[Point]) -> float:
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))) / 2


def _dist_to_segment(p: Point, a: Point, b: Point) -> Tuple[float, Point]:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    q = (ax + t * dx, ay + t * dy)
    return math.hypot(p[0] - q[0], p[1] - q[1]), q


class LabelModel:
    """The shapes of one image, editable. Every change that the user can undo goes through `begin_change()` first
    (the editor calls it once at the start of a drag, so a whole drag is one undo step)."""

    def __init__(self, shapes: Sequence[Shape] = ()):
        self.shapes: List[Shape] = list(shapes)
        self._undo: List[List[Shape]] = []
        self._redo: List[List[Shape]] = []
        self._saved = self._snapshot()

    # ---- state ---------------------------------------------------------------------
    def _snapshot(self) -> List[Shape]:
        return list(self.shapes)

    def begin_change(self) -> None:
        self._undo.append(self._snapshot())
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self.shapes = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self.shapes = self._redo.pop()
        return True

    @property
    def dirty(self) -> bool:
        return self.shapes != self._saved

    def mark_saved(self) -> None:
        self._saved = self._snapshot()

    def to_text(self) -> str:
        return format_labels(self.shapes)

    # ---- what is under a point -----------------------------------------------------
    @staticmethod
    def handles(shape: Shape) -> List[Point]:
        """The points that can be dragged: the 4 corners of a box (clockwise from the top left) or the vertices."""
        if shape.is_box:
            (x1, y1), (x2, y2) = shape.points
            return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        return list(shape.points)

    def handle_at(self, x: float, y: float, tol: float, only: Optional[int] = None) -> Optional[Tuple[int, int]]:
        """(shape index, handle index) of the nearest handle within `tol`; the shapes drawn last win."""
        best: Optional[Tuple[float, int, int]] = None
        order = [only] if only is not None else range(len(self.shapes) - 1, -1, -1)
        for si in order:
            for hi, (hx, hy) in enumerate(self.handles(self.shapes[si])):
                d = math.hypot(hx - x, hy - y)
                if d <= tol and (best is None or d < best[0]):
                    best = (d, si, hi)
        return None if best is None else (best[1], best[2])

    def shape_at(self, x: float, y: float) -> Optional[int]:
        """The shape containing the point; the smallest one when several do (so a small object inside a big one
        can still be picked)."""
        hits = []
        for si, s in enumerate(self.shapes):
            pts = self.handles(s)
            if _inside(pts, x, y):
                hits.append((_area(pts), si))
        return min(hits)[1] if hits else None

    # ---- changes ----------------------------------------------------------------------
    def move_handle(self, si: int, hi: int, x: float, y: float) -> None:
        s = self.shapes[si]
        x, y = _clamp(x), _clamp(y)
        if s.is_box:
            (x1, y1), (x2, y2) = s.points
            if hi in (0, 3):
                x1 = x
            else:
                x2 = x
            if hi in (0, 1):
                y1 = y
            else:
                y2 = y
            self.shapes[si] = Shape(s.cls, ((min(x1, x2), min(y1, y2)), (max(x1, x2), max(y1, y2))))
        else:
            pts = list(s.points)
            pts[hi] = (x, y)
            self.shapes[si] = Shape(s.cls, tuple(pts))

    def move_shape(self, si: int, dx: float, dy: float) -> None:
        """Moves a whole shape, stopping at the edges of the image (the shape is never squeezed)."""
        s = self.shapes[si]
        xs, ys = [p[0] for p in s.points], [p[1] for p in s.points]
        dx = max(-min(xs), min(1.0 - max(xs), dx))
        dy = max(-min(ys), min(1.0 - max(ys), dy))
        self.shapes[si] = Shape(s.cls, tuple((px + dx, py + dy) for px, py in s.points))

    def add_box(self, cls: int, x1: float, y1: float, x2: float, y2: float) -> Optional[int]:
        a, b = (min(_clamp(x1), _clamp(x2)), min(_clamp(y1), _clamp(y2))), \
               (max(_clamp(x1), _clamp(x2)), max(_clamp(y1), _clamp(y2)))
        if b[0] - a[0] < MIN_SIDE or b[1] - a[1] < MIN_SIDE:
            return None
        self.shapes.append(Shape(cls, (a, b)))
        return len(self.shapes) - 1

    def add_polygon(self, cls: int, points: Sequence[Point]) -> Optional[int]:
        pts = tuple((_clamp(x), _clamp(y)) for x, y in points)
        if len(pts) < 3 or _area(pts) < MIN_SIDE * MIN_SIDE:
            return None
        self.shapes.append(Shape(cls, pts))
        return len(self.shapes) - 1

    def delete(self, si: int) -> None:
        del self.shapes[si]

    def set_class(self, si: int, cls: int) -> None:
        s = self.shapes[si]
        self.shapes[si] = Shape(cls, s.points)

    def insert_vertex(self, si: int, x: float, y: float, tol: float) -> Optional[int]:
        """Adds a vertex on the polygon edge nearest to the point, if one is within `tol`. Returns its index."""
        s = self.shapes[si]
        if s.is_box:
            return None
        pts = list(s.points)
        best: Optional[Tuple[float, int, Point]] = None
        for i in range(len(pts)):
            d, q = _dist_to_segment((x, y), pts[i], pts[(i + 1) % len(pts)])
            if d <= tol and (best is None or d < best[0]):
                best = (d, i, q)
        if best is None:
            return None
        pts.insert(best[1] + 1, best[2])
        self.shapes[si] = Shape(s.cls, tuple(pts))
        return best[1] + 1

    def remove_vertex(self, si: int, hi: int) -> bool:
        s = self.shapes[si]
        if s.is_box or len(s.points) <= 3:
            return False
        self.shapes[si] = Shape(s.cls, tuple(p for i, p in enumerate(s.points) if i != hi))
        return True
