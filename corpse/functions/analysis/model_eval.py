"""Measuring a YOLO model on real photos.

The numbers written when a model is trained say how it did on ITS OWN validation images. This module instead runs
the model on photos that already have labels (the ones approved on the server, corrected by hand) and compares what
it finds with what is in the label file: so two models can be compared on the same photos, which is the only
comparison that means something.

No Qt and no network here: the caller passes the photos already on disk.

Autore: Samuele Gallo
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from common.label_shapes import Shape, parse_labels

Box = Tuple[float, float, float, float]                 # x1, y1, x2, y2 in pixels
IOU_MATCH = 0.5                                         # two boxes are the same object from here up
Progress = Optional[Callable[[int, int], None]]


def shape_box(shape: Shape, width: int, height: int) -> Box:
    """The rectangle around a label (a box, or the outline of a polygon), in pixels."""
    xs = [p[0] * width for p in shape.points]
    ys = [p[1] * height for p in shape.points]
    return min(xs), min(ys), max(xs), max(ys)


def truth_boxes(text: str, width: int, height: int) -> List[Tuple[int, Box]]:
    """What the label file says is in the photo: (class, rectangle)."""
    return [(s.cls, shape_box(s, width, height)) for s in parse_labels(text)]


def iou(a: Box, b: Box) -> float:
    """How much two rectangles overlap, between 0 (apart) and 1 (identical)."""
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


@dataclass
class Score:
    """What a model got right and wrong over a set of photos."""
    photos: int = 0
    objects: int = 0                                     # objects written in the labels
    found: int = 0                                       # objects the model found (right or wrong)
    hits: int = 0                                        # found in the right place (and right class)
    wrong_class: int = 0                                 # found in the right place but called something else
    overlaps: List[float] = field(default_factory=list)  # the overlap of each hit
    per_class: Dict[str, Dict[str, int]] = field(default_factory=dict)

    @property
    def missed(self) -> int:
        return max(0, self.objects - self.hits)

    @property
    def false_alarms(self) -> int:
        return max(0, self.found - self.hits)

    @property
    def precision(self) -> float:
        return self.hits / self.found if self.found else 0.0

    @property
    def recall(self) -> float:
        return self.hits / self.objects if self.objects else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    @property
    def mean_overlap(self) -> float:
        return sum(self.overlaps) / len(self.overlaps) if self.overlaps else 0.0

    def summary(self) -> Dict[str, Any]:
        return {"photos": self.photos, "objects": self.objects, "found": self.found, "hits": self.hits,
                "missed": self.missed, "false_alarms": self.false_alarms, "wrong_class": self.wrong_class,
                "precision": round(self.precision, 3), "recall": round(self.recall, 3), "f1": round(self.f1, 3),
                "mean_overlap": round(self.mean_overlap, 3), "per_class": self.per_class}


def _count(score: Score, name: str, field_name: str) -> None:
    score.per_class.setdefault(name, {"objects": 0, "hits": 0, "missed": 0, "false_alarms": 0})[field_name] += 1


def compare(truth: Sequence[Tuple[int, Box]], found: Sequence[Tuple[int, Box]], names: Sequence[str],
            score: Score, min_overlap: float = IOU_MATCH) -> None:
    """Pairs what the model found with what the labels say, each object used once, the best overlap first."""
    pairs = sorted(((iou(t[1], f[1]), ti, fi) for ti, t in enumerate(truth) for fi, f in enumerate(found)),
                   reverse=True)
    used_t, used_f = set(), set()
    score.objects += len(truth)
    score.found += len(found)
    for cls, _box in truth:
        _count(score, class_name(names, cls), "objects")
    for overlap, ti, fi in pairs:
        if overlap < min_overlap or ti in used_t or fi in used_f:
            continue
        used_t.add(ti)
        used_f.add(fi)
        same_class = truth[ti][0] == found[fi][0]
        if same_class:
            score.hits += 1
            score.overlaps.append(overlap)
            _count(score, class_name(names, truth[ti][0]), "hits")
        else:
            score.wrong_class += 1
    for ti, (cls, _b) in enumerate(truth):
        if ti not in used_t:
            _count(score, class_name(names, cls), "missed")
    for fi, (cls, _b) in enumerate(found):
        if fi not in used_f:
            _count(score, class_name(names, cls), "false_alarms")


def class_name(names: Sequence[str], index: int) -> str:
    return names[index] if 0 <= index < len(names) else str(index)


def evaluate(detect: Callable[[Path], Tuple[List[Tuple[int, Box]], Sequence[str], int, int]],
             photos: Sequence[Tuple[Path, str]], progress: Progress = None,
             min_overlap: float = IOU_MATCH) -> Score:
    """`photos` are (file, text of its labels); `detect(file)` returns what the model finds there, the class names
    and the size of the photo. A photo that cannot be read is skipped."""
    score = Score()
    for i, (path, labels) in enumerate(photos, 1):
        try:
            found, names, width, height = detect(Path(path))
            if width and height:
                score.photos += 1
                compare(truth_boxes(labels, width, height), found, names, score, min_overlap)
        except Exception:                                # noqa: BLE001 - a broken photo must not stop the test
            pass
        if progress:
            progress(i, len(photos))                     # the count goes on: a skipped photo is still one done
    return score


def yolo_detector(model_path: Path, device: str = "") -> Callable[[Path], Tuple[List[Tuple[int, Box]],
                                                                                List[str], int, int]]:
    """A `detect` for `evaluate` that uses a YOLO model (imported only here: the tests do without it)."""
    from ultralytics import YOLO
    model = YOLO(str(model_path))
    names = model.names
    ordered = [str(names[k]) for k in sorted(names)] if isinstance(names, dict) else [str(n) for n in names]

    def detect(path: Path):
        result = model.predict(str(path), device=device or None, verbose=False)[0]
        height, width = result.orig_shape
        found = []
        for box in result.boxes or []:
            x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
            found.append((int(box.cls.item()), (x1, y1, x2, y2)))
        return found, ordered, int(width), int(height)

    return detect
