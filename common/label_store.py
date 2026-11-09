"""Labels that the metrological analysis produced for a photo or a video, kept apart from the media.

Each analysed file gets a label file in YOLO format in a folder of the app (never next to the original, which may be
read-only or belong to somebody else), plus the list of class names the numbers refer to:

  photo   one line per object, `cls cx cy w h` (box) or `cls x1 y1 x2 y2 ...` (polygon), coordinates 0..1
  video   the same lines with the frame number in front: `frame cls ...`
  classes one class name per line (line N = class N)

When the media is uploaded to the server the label file travels with it (same name, `.txt`) and stays associated
with it in the catalog. Qt-free: used by the analysis and by the uploads."""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple, Union

from common.paths import LOCAL_DIR

LABELS_DIR = LOCAL_DIR / "labels"
CLASSES_NAME = "classes.txt"

PathLike = Union[str, Path]


def _key(media: PathLike) -> str:
    media = Path(media)
    digest = hashlib.sha1(str(media.resolve()).encode("utf-8")).hexdigest()[:12]
    return f"{media.stem}_{digest}"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def label_paths(media: PathLike, base: Optional[Path] = None) -> Tuple[Path, Path]:
    """(label file, classes file) for a media file; they may not exist yet."""
    base = Path(base) if base else LABELS_DIR
    key = _key(media)
    return base / f"{key}.txt", base / f"{key}.classes.txt"


def yolo_box_line(cls: int, bbox_xyxy: Sequence[float], width: int, height: int) -> str:
    """`cls cx cy w h`, normalised to 0..1 and clipped to the image."""
    x1, y1, x2, y2 = (float(v) for v in bbox_xyxy)
    x1, x2 = sorted((min(max(x1, 0.0), width), min(max(x2, 0.0), width)))
    y1, y2 = sorted((min(max(y1, 0.0), height), min(max(y2, 0.0), height)))
    return (f"{cls} {(x1 + x2) / 2 / width:.6f} {(y1 + y2) / 2 / height:.6f} "
            f"{(x2 - x1) / width:.6f} {(y2 - y1) / height:.6f}")


def yolo_polygon_line(cls: int, points: Iterable[Sequence[float]], width: int, height: int) -> str:
    """`cls x1 y1 x2 y2 ...` (segmentation), normalised and clipped; needs at least 3 points."""
    pts = [(min(max(float(x), 0.0), width) / width, min(max(float(y), 0.0), height) / height) for x, y in points]
    if len(pts) < 3:
        raise ValueError("A polygon needs at least 3 points.")
    return f"{cls} " + " ".join(f"{x:.6f} {y:.6f}" for x, y in pts)


def save_labels(media: PathLike, lines: Sequence[str], classes: Sequence[str], base: Optional[Path] = None) -> Path:
    """Stores the label lines of a media file (replacing earlier ones) and its class names. Returns the label file."""
    label, names = label_paths(media, base)
    _write(label, "".join(line + "\n" for line in lines))
    _write(names, "".join(c + "\n" for c in classes))
    return label


def find_labels(media: PathLike, base: Optional[Path] = None) -> Optional[Tuple[Path, Optional[Path]]]:
    """The saved label file of a media file and its classes file (None if it has none)."""
    label, names = label_paths(media, base)
    if not label.is_file():
        return None
    return label, (names if names.is_file() else None)


def sidecars(media: PathLike, base: Optional[Path] = None) -> Tuple[Optional[Path], Optional[Path]]:
    """What goes with a media file when it is sent: (label file, classes file). A label file next to the media
    (same name, `.txt`) wins over the one saved by the analysis; the classes file next to the media is `classes.txt`."""
    media = Path(media)
    beside = media.with_suffix(".txt")
    beside_classes = media.parent / CLASSES_NAME
    saved = find_labels(media, base)
    label = beside if beside.is_file() else (saved[0] if saved else None)
    classes = beside_classes if beside_classes.is_file() else (saved[1] if saved else None)
    return label, classes


def class_list(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def read_labels(media: PathLike, base: Optional[Path] = None) -> Tuple[str, List[str], bool]:
    """What the editor starts from: (label text, class names, whether the label file sits next to the media).
    Both are empty for a media file without labels."""
    media = Path(media)
    label, classes = sidecars(media, base)
    text = label.read_text(encoding="utf-8", errors="replace") if label else ""
    names = class_list(classes.read_text(encoding="utf-8", errors="replace")) if classes else []
    return text, names, label is not None and label == media.with_suffix(".txt")


def write_labels(media: PathLike, text: str, classes: Sequence[str], beside: bool, base: Optional[Path] = None) -> Path:
    """Saves edited labels where they came from: next to the media when that is where they were (they would win over
    anything saved elsewhere), otherwise in the label store."""
    media = Path(media)
    if beside:
        _write(media.with_suffix(".txt"), text)
        _write(media.parent / CLASSES_NAME, "".join(c + "\n" for c in classes))
        return media.with_suffix(".txt")
    label, names = label_paths(media, base)
    _write(label, text)
    _write(names, "".join(c + "\n" for c in classes))
    return label
