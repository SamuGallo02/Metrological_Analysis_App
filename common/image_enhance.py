"""Improved copies of photos and videos.

A media file keeps its original: the improved version is written beside it, in an `enhanced/` folder with the same
name (`photos/a.jpg` -> `photos/enhanced/a.jpg`). Labels, measurements and the upload all keep working on the
original, and the server stores the pair the same way.

The algorithm itself is not part of this module: whoever has one registers it with `register()`, and the rest of the
application (interface, upload, server) works without knowing what it does. Until something is registered,
`available()` is empty and the application simply does not offer the improvement.

Autore: Samuele Gallo
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

from common.params import ENHANCED_DIR, IMAGE_SUFFIXES, VIDEO_SUFFIXES

PathLike = Union[str, Path]
# name of the method -> function that reads `src` and writes the improved file to `dst`
Enhancer = Callable[[Path, Path], None]
_METHODS: Dict[str, Enhancer] = {}


def register(name: str, enhancer: Enhancer) -> None:
    """Adds a way of improving an image or a video."""
    _METHODS[name] = enhancer


def available() -> List[str]:
    """The methods installed, in the order they were registered (empty: nothing to offer)."""
    return list(_METHODS)


def enhanced_path(media: PathLike) -> Path:
    """Where the improved copy of a file goes: `enhanced/` beside it, with the same name."""
    media = Path(media)
    return media.parent / ENHANCED_DIR / media.name


def original_path(enhanced: PathLike) -> Path:
    """The inverse: from the improved copy back to its original."""
    enhanced = Path(enhanced)
    return enhanced.parent.parent / enhanced.name


def is_enhanced(media: PathLike) -> bool:
    return Path(media).parent.name == ENHANCED_DIR


def find_enhanced(media: PathLike) -> Optional[Path]:
    """The improved copy of a file, if it has been made."""
    path = enhanced_path(media)
    return path if path.is_file() else None


def can_improve(media: PathLike) -> bool:
    suffix = Path(media).suffix.lower()
    return bool(_METHODS) and not is_enhanced(media) and suffix in set(IMAGE_SUFFIXES) | set(VIDEO_SUFFIXES)


def improve(media: PathLike, method: str = "", replace: bool = False) -> Path:
    """Writes the improved copy of `media` and returns its path. With `replace=False` an existing copy is kept.
    Raises LookupError if no method is installed, and leaves nothing behind if the method fails."""
    if not _METHODS:
        raise LookupError("no image improvement installed")
    name = method or next(iter(_METHODS))
    if name not in _METHODS:
        raise LookupError(f"unknown method: {name}")
    media = Path(media)
    dest = enhanced_path(media)
    if dest.is_file() and not replace:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    try:
        _METHODS[name](media, tmp)
        tmp.replace(dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return dest
