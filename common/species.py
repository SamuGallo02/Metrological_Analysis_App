"""Which species a photo or a video belongs to.

The answer is in its labels: every label carries a class, and the class is the species. A photo of two animals
has two labels and therefore belongs to two species - it is shown under both, without being copied anywhere.

So the views of the media are built here, from the files the user registered, and the folders the user put in
stay as they are: the species are a way of looking at them, not a place where they are moved.

Qt-free, so the interface, the analysis and the tests can all use it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from common.label_shapes import Shape, format_labels, parse_labels, parse_video_labels
from common.label_store import read_labels, write_labels
from common.params import VIDEO_SUFFIXES

UNNAMED = ""                       # the group of the files that carry no label yet
WHOLE = ((0.0, 0.0), (1.0, 1.0))   # "the whole picture is this species", until somebody draws it properly
_cache: Dict[Tuple[str, int, int], List[str]] = {}


def _is_video(media: Path) -> bool:
    return media.suffix.lower() in tuple(VIDEO_SUFFIXES)


def shapes_of(media: Path) -> Dict[int, List[Shape]]:
    """The labels of a file, by frame (a photo has only frame 0)."""
    text, _names, _beside = read_labels(media)
    if not text.strip():
        return {}
    return parse_video_labels(text) if _is_video(media) else {0: parse_labels(text)}


def species_of(media: Path) -> List[str]:
    """The species of a file, in the order the classes appear. Empty when it has no labels yet."""
    media = Path(media)
    try:
        st = media.stat()
        key = (str(media), int(st.st_mtime), st.st_size)
    except OSError:
        return []
    known = _cache.get(key)
    if known is not None:
        return list(known)
    text, names, _beside = read_labels(media)
    found: List[str] = []
    if text.strip():
        shapes = parse_video_labels(text) if _is_video(media) else {0: parse_labels(text)}
        for frame in shapes.values():
            for s in frame:
                name = names[s.cls] if 0 <= s.cls < len(names) else str(s.cls)
                if name not in found:
                    found.append(name)
    if len(_cache) > 20000:
        _cache.clear()
    _cache[key] = found
    return list(found)


def forget(media: Optional[Path] = None) -> None:
    """After an edit: the species of that file (or of all of them) are read again."""
    if media is None:
        return _cache.clear()
    for key in [k for k in _cache if k[0] == str(Path(media))]:
        _cache.pop(key, None)


def by_species(files: Iterable[Path]) -> Dict[str, List[Path]]:
    """{species: files}. A file with two species is in both lists; one with no labels is under UNNAMED."""
    out: Dict[str, List[Path]] = {}
    for f in files:
        names = species_of(f) or [UNNAMED]
        for name in names:
            out.setdefault(name, []).append(f)
    return out


def known_species(files: Iterable[Path]) -> List[str]:
    """The species already used among these files, in alphabetical order."""
    return sorted({name for f in files for name in species_of(f)}, key=str.lower)


def assign(media: Path, species: str, frame: int = 0) -> bool:
    """Files a photo or a video under a species, with a label of the user's own: if it has no label of that
    species yet, one covering the whole picture is added, ready to be redrawn in the editor. False when it was
    already there. The file itself is never moved or copied: only its labels say where it belongs."""
    media, species = Path(media), species.strip()
    if not species:
        return False
    text, names, beside = read_labels(media)
    if species in species_of(media):
        return False
    shapes = parse_video_labels(text) if _is_video(media) else {0: parse_labels(text)}
    if species in names:
        cls = names.index(species)
    else:
        cls = len(names)
        names = list(names) + [species]
    shapes.setdefault(frame, []).append(Shape(cls, WHOLE))
    if _is_video(media):
        from common.label_shapes import format_video_labels
        body = format_video_labels(shapes)
    else:
        body = format_labels(shapes.get(0, []))
    write_labels(media, body, names, beside)
    forget(media)
    return True


def assign_many(files: Sequence[Path], species: str) -> int:
    """Files several photos or videos under one species. Returns how many of them it actually changed."""
    return sum(1 for f in files if assign(Path(f), species))


def common_species(files: Sequence[Path]) -> str:
    """The species these files share, when they all carry exactly the same one (used to suggest it on upload)."""
    sets = [set(species_of(Path(f))) for f in files]
    shared = set.intersection(*sets) if sets else set()
    return sorted(shared)[0] if len(shared) == 1 else ""
