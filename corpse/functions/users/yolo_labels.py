"""YOLO label files for the photo viewer: where to look for them (no Qt, no network). Reading and writing the
lines is in `common.label_shapes`."""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import List

from common.label_shapes import Shape, class_label, format_labels, parse_labels  # noqa: F401  (re-exported)
from common.model_metadata import classes_from_yaml_text


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

