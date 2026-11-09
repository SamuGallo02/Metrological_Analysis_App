"""Structure of the media (photos, stereo photos, videos) a user sends for a species, and how they are numbered when
approved. Labels are YOLO `.txt` files with the same name as the media they describe."""
from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath
from typing import Dict, List, Set, Tuple

from common.errors import AppError

from .params import (KIND_PHOTOS, KIND_STEREO, KIND_VIDEO, LABEL_SUFFIX, SPECIES_EXAMPLE, SPECIES_IMAGE_EXT,
                     SPECIES_MONO_EXAMPLE, SPECIES_RE, SPECIES_STEREO_EXAMPLE, SPECIES_VIDEO_EXAMPLE,
                     SPECIES_VIDEO_EXT, STEREO_SIDES)

PREFIX = {KIND_PHOTOS: "IMG", KIND_STEREO: "IMG", KIND_VIDEO: "VID"}
CLASSES_FILE = "classes.txt"             # the class names the label numbers refer to: one per line, in the media folder


def media_suffixes(kind: str) -> Set[str]:
    return set(SPECIES_VIDEO_EXT if kind == KIND_VIDEO else SPECIES_IMAGE_EXT)


def label_name(media: str) -> str:
    """The label file of a media file: same name, `.txt`."""
    return str(PurePosixPath(media).with_suffix(LABEL_SUFFIX))


def check_media_file(kind: str, rel: str) -> Tuple[str, ...]:
    """Validates the path of an uploaded file (relative to its area) before receiving it."""
    parts = tuple(p for p in rel.split("/") if p)
    if not parts or not re.fullmatch(SPECIES_RE, parts[0]):
        raise AppError("The first folder must be named after the scientific name (Genus species), "
                       "for example {example}.", 422, example=SPECIES_EXAMPLE)
    if kind == KIND_STEREO:
        ok = len(parts) == 3 and parts[1] in STEREO_SIDES              # <Species>/<lx|rx>/<file>
        example = SPECIES_STEREO_EXAMPLE
    else:
        ok = len(parts) == 2                                           # <Species>/<file>
        example = SPECIES_VIDEO_EXAMPLE if kind == KIND_VIDEO else SPECIES_MONO_EXAMPLE
    if not ok:
        raise AppError("Wrong folder structure: use for example {example}.", 422, example=example)
    ext = PurePosixPath(parts[-1]).suffix.lower()
    if ext != LABEL_SUFFIX and ext not in media_suffixes(kind):
        raise AppError("Extension {ext} is not allowed in this area.", 415, ext=ext or "(none)")
    return parts


def _files(folder: Path) -> List[Path]:
    if not folder.is_dir() or folder.is_symlink():
        return []
    return [p for p in folder.iterdir() if p.is_file() and not p.is_symlink()]


def _media_names(folder: Path, kind: str) -> Set[str]:
    ok = media_suffixes(kind)
    return {p.name for p in _files(folder) if p.suffix.lower() in ok}


def count_media(folder: Path, kind: str) -> int:
    """Number of media files (labels not counted) at any depth."""
    ok = media_suffixes(kind)
    return sum(1 for p in Path(folder).rglob("*") if p.is_file() and p.suffix.lower() in ok)


def count_labelled(folder: Path) -> int:
    return sum(1 for p in Path(folder).rglob("*")
               if p.is_file() and p.suffix.lower() == LABEL_SUFFIX and p.name != CLASSES_FILE)


def validate_media_dir(folder: Path, kind: str) -> List[AppError]:
    """The problems of an upload waiting for review (empty list if it is fine)."""
    folder = Path(folder)
    problems: List[AppError] = []
    sides = {s: _media_names(folder / s, kind) for s in STEREO_SIDES}
    has_sides = any((folder / s).is_dir() for s in STEREO_SIDES)
    loose = _media_names(folder, kind)

    if kind == KIND_STEREO:
        if loose:
            problems.append(AppError("Wrong folder structure: use for example {example}.", 422,
                                     example=SPECIES_STEREO_EXAMPLE))
        if not has_sides or not all(sides.values()):
            problems.append(AppError("The stereo folder '{folder}' needs both an rx and an lx subfolder "
                                     "containing photos.", 422, folder=folder.name))
        elif sides["lx"] != sides["rx"]:
            problems.append(AppError("The lx and rx folders must contain photos with the same names.", 422))
        groups = [folder / s for s in STEREO_SIDES]
    else:
        example = SPECIES_VIDEO_EXAMPLE if kind == KIND_VIDEO else SPECIES_MONO_EXAMPLE
        if has_sides:
            problems.append(AppError("Wrong folder structure: use for example {example}.", 422, example=example))
        if not loose:
            problems.append(AppError("No photos found in '{folder}'.", 422, folder=folder.name))
        groups = [folder]
    for group in groups:                                               # a label must describe a media of its folder
        media_stems = {Path(n).stem for n in _media_names(group, kind)}
        for p in _files(group):
            if p.suffix.lower() == LABEL_SUFFIX and p.name != CLASSES_FILE and p.stem not in media_stems:
                problems.append(AppError("The label file '{name}' has no matching photo or video.", 422, name=p.name))
                break
    return problems


def move_numbered(src: Path, dst: Path, kind: str) -> int:
    """Moves the media of `src` into `dst` as IMG_0001, IMG_0002... (VID_ for videos) in alphabetical order of the
    original names; each label follows its media. Nothing stays behind in `src` that was moved, so the data is never
    held twice. In a stereo upload the same name gets the same number in lx and rx, so the pairs stay together.
    Needs a folder that already passed `validate_media_dir`. On an error the files already moved go back.
    Returns how many media files were moved."""
    sides = [s for s in STEREO_SIDES if (src / s).is_dir()] if kind == KIND_STEREO else []
    sources = [src / s for s in sides] or [src]
    targets = [dst / s for s in sides] or [dst]
    names = sorted(_media_names(sources[0], kind))
    done: List[Tuple[Path, Path]] = []
    try:
        for target in targets:
            target.mkdir(parents=True, exist_ok=True)
        for number, name in enumerate(names, 1):
            stem = f"{PREFIX[kind]}_{number:04d}"
            for source, target in zip(sources, targets):
                for old in (source / name, source / label_name(name)):
                    if old.is_file():
                        new = target / (stem + old.suffix.lower())
                        os.replace(old, new)
                        done.append((old, new))
        for source, target in zip(sources, targets):                   # the class names stay with the labels
            names_file = source / CLASSES_FILE
            if names_file.is_file():
                os.replace(names_file, target / CLASSES_FILE)
                done.append((names_file, target / CLASSES_FILE))
    except BaseException:
        for old, new in reversed(done):                                # put everything back
            try:
                os.replace(new, old)
            except OSError:
                pass
        raise
    return len(names) * len(sources)
