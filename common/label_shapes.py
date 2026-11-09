"""YOLO label lines as shapes: reading and writing (no Qt, no network). Shared by the viewer and the label editor."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple


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


def format_labels(shapes: Sequence[Shape]) -> str:
    """The inverse of `parse_labels`: a box becomes `cls cx cy w h`, a polygon `cls x1 y1 x2 y2 ...`."""
    lines = []
    for s in shapes:
        if s.is_box:
            (x1, y1), (x2, y2) = s.points
            lines.append(f"{s.cls} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {abs(x2 - x1):.6f} {abs(y2 - y1):.6f}")
        else:
            lines.append(f"{s.cls} " + " ".join(f"{x:.6f} {y:.6f}" for x, y in s.points))
    return "".join(line + "\n" for line in lines)


def class_label(names: Optional[List[str]], cls: int) -> str:
    return names[cls] if names and 0 <= cls < len(names) else str(cls)


def parse_video_labels(text: str) -> Dict[int, List[Shape]]:
    """Reads the labels of a video: every line starts with the frame number, then a normal label line."""
    frames: Dict[int, List[Shape]] = {}
    for line in text.splitlines():
        head, _, rest = line.strip().partition(" ")
        if not head.isdigit():
            continue
        shapes = parse_labels(rest)
        if shapes:
            frames.setdefault(int(head), []).extend(shapes)
    return frames


def format_video_labels(frames: Dict[int, Sequence[Shape]]) -> str:
    """The inverse of `parse_video_labels` (frames in order, empty frames left out)."""
    out = []
    for frame in sorted(frames):
        out.extend(f"{frame} {line}" for line in format_labels(frames[frame]).splitlines())
    return "".join(line + "\n" for line in out)
