"""
Module for Managing the Analyzable Object Classes
=============================================================
Maintains a persistent list (JSON file) of the object categories
selectable in the GUI to filter YOLO detections (e.g. "people",
"vehicles", "animals"...). The list can be edited at runtime through
add_class()/remove_class() and is saved to disk between sessions.

Note: the class name must match (case-insensitive) the label
returned by the YOLO model in use (predictions.names), otherwise the filter
will find no matches. If the model is in English (e.g. "person", "car"),
enter the label exactly as the model returns it.

Autore: Samuele Gallo
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from common.paths import CLASSES_FILE  # noqa: E402

# Special value meaning "no filter, show all detected objects"
ALL_OBJECTS = "Tutti gli oggetti"


def load_classes(path: Path = CLASSES_FILE) -> List[str]:
    """Loads the list of saved classes. Returns an empty list if the file does not exist or is corrupted."""
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [str(x) for x in data]
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_classes(classes: List[str], path: Path = CLASSES_FILE) -> None:
    """Saves the list of classes to file, sorted and without duplicates."""
    unique_sorted = sorted(dict.fromkeys(c.strip() for c in classes if c.strip()))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(unique_sorted, f, ensure_ascii=False, indent=2)


def add_class(name: str, path: Path = CLASSES_FILE) -> List[str]:
    """Adds a new class (if not already present, case-insensitive) and saves. Returns the updated list."""
    name = name.strip()
    classes = load_classes(path)
    if name and name.lower() not in (c.lower() for c in classes):
        classes.append(name)
        save_classes(classes, path)
    return load_classes(path)


def remove_class(name: str, path: Path = CLASSES_FILE) -> List[str]:
    """Removes a class (case-insensitive) and saves. Returns the updated list."""
    classes = [c for c in load_classes(path) if c.lower() != name.strip().lower()]
    save_classes(classes, path)
    return classes