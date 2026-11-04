"""Folder structure required for the photos of a species."""
from __future__ import annotations

import re
import shutil
from pathlib import Path, PurePosixPath
from typing import List, Tuple, Set

from common.errors import AppError

from .params import (SPECIES_EXAMPLE, SPECIES_IMAGE_EXT, SPECIES_MONO_EXAMPLE, 
                     SPECIES_RE, SPECIES_SIDES, SPECIES_STEREO_EXAMPLE)


def check_species_file(rel: str) -> Tuple[str, ...]:
    parts = tuple(p for p in rel.split("/") if p)
    if not parts or not re.fullmatch(SPECIES_RE, parts[0]):
        raise AppError("The first folder must be named after the scientific name (Genus species), "
                       "for example {example}.", 422, example=SPECIES_EXAMPLE)

    mono = len(parts) == 2                                       # <Specie>/<foto>
    stereo = len(parts) == 3 and parts[1] in SPECIES_SIDES       # <Specie>/<lx|rx>/<foto>
    if not (mono or stereo):
        raise AppError("Wrong folder structure: use for example {mono} or {stereo}.", 422,
                       mono=SPECIES_MONO_EXAMPLE, stereo=SPECIES_STEREO_EXAMPLE)

    ext = PurePosixPath(parts[-1]).suffix.lower()
    if ext not in SPECIES_IMAGE_EXT:
        raise AppError("Extension {ext} is not allowed in this area.", 415, ext=ext or "(none)")
    return parts


def _image_names(folder: Path) -> Set[str]:
    if not folder.is_dir() or folder.is_symlink():
        return set()
    return {p.name for p in folder.iterdir()
            if p.is_file() and not p.is_symlink() and p.suffix.lower() in SPECIES_IMAGE_EXT}


def _count_images(folder: Path) -> int:
    return len(_image_names(folder))

def count_photos(species_dir: Path) -> int:
    """Numero di foto in tutta la cartella della specie, a qualsiasi profondità."""
    return sum(1 for p in species_dir.rglob("*") if p.is_file() and p.suffix.lower() in SPECIES_IMAGE_EXT)


def validate_species_dir(species_dir: Path) -> List[AppError]:
    species_dir = Path(species_dir)
    problems: List[AppError] = []
    loose = _count_images(species_dir)                                  # foto direttamente nella cartella (mono)
    sides = {side: _image_names(species_dir / side) for side in SPECIES_SIDES}
    has_stereo = any((species_dir / side).is_dir() for side in SPECIES_SIDES)

    if not has_stereo:
        if loose == 0:
            problems.append(AppError("No photos found in '{folder}'.", 422, folder=species_dir.name))
        return problems

    if loose:                                                           # foto sciolte E cartelle lx/rx insieme
        problems.append(AppError("Wrong folder structure: use for example {mono} or {stereo}.", 422,
                                 mono=SPECIES_MONO_EXAMPLE, stereo=SPECIES_STEREO_EXAMPLE))
    if not all(sides.values()):
        problems.append(AppError("The stereo folder '{folder}' needs both an rx and an lx subfolder "
                                 "containing photos.", 422, folder=species_dir.name))
    elif sides["lx"] != sides["rx"]:
        problems.append(AppError("The lx and rx folders must contain photos with the same names.", 422))
    return problems

def copy_numbered(src: Path, dst: Path) -> int:
    """Copia le foto di src in dst chiamandole IMG_0001, IMG_0002... in ordine alfabetico dei nomi originali.

    Presuppone che src abbia già passato validate_species_dir. In una cartella stereo lo stesso nome originale
    prende lo stesso numero in lx e in rx, quindi le coppie restano unite. Ritorna quanti file ha copiato."""
    sides = [s for s in SPECIES_SIDES if (src / s).is_dir()]
    sources = [src / s for s in sides] or [src]
    targets = [dst / s for s in sides] or [dst]
    names = sorted(_image_names(sources[0]))
    for target in targets:
        target.mkdir(parents=True, exist_ok=True)
    for number, name in enumerate(names, 1):
        new_name = f"IMG_{number:04d}{Path(name).suffix.lower()}"
        for source, target in zip(sources, targets):
            shutil.copy2(source / name, target / new_name)
    return len(names) * len(sources)