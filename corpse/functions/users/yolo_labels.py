"""YOLO label files for the photo viewer: where to look for them and how to read them (no Qt, no network)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import List, Optional, Tuple

from common.model_metadata import classes_from_yaml_text


@dataclass(frozen=True)
class Shape:
    """One labelled object. Coordinates are normalised (0..1): a box has 2 points (corners), a polygon 3 or more."""
    cls: int
    points: Tuple[Tuple[float, float], ...]

    @property
    def is_box(self) -> bool:
        return len(self.points) == 2


def parse_labels(text: str) -> List[Shape]:
    """Reads a YOLO .txt file: `cls cx cy w h` (box, an optional trailing confidence is ignored) or
    `cls x1 y1 x2 y2 ...` (segmentation polygon). Malformed lines are skipped."""
    shapes: List[Shape] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            cls = int(float(parts[0]))
            nums = [float(v) for v in parts[1:]]
        except ValueError:
            continue
        if cls < 0 or not all(math.isfinite(v) for v in nums):
            continue
        if len(nums) in (4, 5):                              # box (the 5th number would be a confidence)
            cx, cy, w, h = nums[:4]
            shapes.append(Shape(cls, ((cx - w / 2, cy - h / 2), (cx + w / 2, cy + h / 2))))
        elif len(nums) >= 6 and len(nums) % 2 == 0:
            shapes.append(Shape(cls, tuple((nums[i], nums[i + 1]) for i in range(0, len(nums), 2))))
    return shapes


def label_candidates(image_rel: str) -> List[str]:
    """Where the label file of an image may be, most likely first: next to it, or in the `labels` folder that
    mirrors `images` (the YOLO dataset layout)."""
    p = PurePosixPath(image_rel)
    out = [str(p.with_suffix(".txt"))]
    parts = list(p.parts)
    for i in range(len(parts) - 2, -1, -1):                  # the nearest `images` folder in the path
        if parts[i].lower() == "images":
            mirrored = PurePosixPath(*parts[:i], "labels", *parts[i + 1:]).with_suffix(".txt")
            out.append(str(mirrored))
            break
    else:
        out.append(str(p.parent / "labels" / (p.stem + ".txt")))
    return out


def names_candidates(image_rel: str) -> List[str]:
    """Files that may hold the class names: data.yaml / classes.txt in the image folder and its parents."""
    out: List[str] = []
    folder = PurePosixPath(image_rel).parent
    while True:
        for name in ("data.yaml", "classes.txt"):
            out.append(str(folder / name) if str(folder) != "." else name)
        if str(folder) in (".", ""):
            break
        folder = folder.parent
    return out


def class_names(file_name: str, text: str) -> List[str]:
    """Names from a data.yaml (`names:`) or a classes.txt (one per line)."""
    if file_name.lower().endswith((".yaml", ".yml")):
        return classes_from_yaml_text(text)
    return [line.strip() for line in text.splitlines() if line.strip()]


def class_label(names: Optional[List[str]], cls: int) -> str:
    return names[cls] if names and 0 <= cls < len(names) else str(cls)
