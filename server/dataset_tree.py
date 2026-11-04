"""Folder structure required for a dataset ready for YOLO: images, labels and data.yaml."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import List, Optional

from common.errors import AppError

from .params import SPECIES_IMAGE_EXT

DATA_FILES = ("data.yaml", "data.yml")


def _label_for(image: PurePosixPath) -> Optional[PurePosixPath]:
    """Where the label of an image must be: the same path with the last folder named images replaced
    by labels, and the extension .txt. None if the image is not inside a folder named images."""
    folders = list(image.parts[:-1])
    for i in range(len(folders) - 1, -1, -1):
        if folders[i] == "images":
            folders[i] = "labels"
            return PurePosixPath(*folders, image.stem + ".txt")
    return None


def validate_dataset_dir(folder: Path) -> List[AppError]:
    """The problems of a dataset folder (empty list if it is valid). Images and labels must correspond
    one to one by name; other files are ignored."""
    folder = Path(folder)
    files = [PurePosixPath(p.relative_to(folder).as_posix()) for p in folder.rglob("*")
             if p.is_file() and not p.is_symlink()]
    problems: List[AppError] = []
    if not any((folder / name).is_file() for name in DATA_FILES):
        problems.append(AppError("The dataset must contain a data.yaml file.", 422))

    images = [f for f in files if f.suffix.lower() in SPECIES_IMAGE_EXT]
    if not images:
        problems.append(AppError("The dataset contains no images.", 422))
        return problems

    labels = {f for f in files if f.suffix.lower() == ".txt" and "labels" in f.parts[:-1]}
    wanted = {image: _label_for(image) for image in images}
    no_label = sorted(str(i) for i, label in wanted.items() if label is None or label not in labels)
    expected = {label for label in wanted.values() if label is not None}
    no_image = sorted(str(label) for label in labels if label not in expected)
    if no_label:
        problems.append(AppError("Images and labels must correspond one to one: "
                                 "{n} images have no label (for example {example}).", 422,
                                 n=len(no_label), example=no_label[0]))
    if no_image:
        problems.append(AppError("Images and labels must correspond one to one: "
                                 "{n} labels have no image (for example {example}).", 422,
                                 n=len(no_image), example=no_image[0]))
    return problems

def count_dataset_images(folder: Path) -> int:
    return sum(1 for p in Path(folder).rglob("*") if p.is_file() and p.suffix.lower() in SPECIES_IMAGE_EXT)