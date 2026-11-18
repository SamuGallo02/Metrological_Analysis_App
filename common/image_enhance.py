"""Improved copies of photos and videos.

A media file keeps its original: the improved version is written beside it, in an `enhanced/` folder with the same
name (`photos/a.jpg` -> `photos/enhanced/a.jpg`). Labels, measurements and the upload all keep working on the
original, and the server stores the pair the same way.

The algorithm itself is not part of this module: whoever has one registers it with `register()`, and the rest of the
application (interface, upload, server) works without knowing what it does. Until something is registered,
`available()` is empty and the application simply does not offer the improvement. `common.enhance_nautilus` is the
one that registers the models of the `nautilus` package, when the libraries for them are installed.

A method can describe itself (a readable name, what it does, which settings it takes): `methods()` hands that over
to the interface, which builds a control for each setting without knowing anything about the algorithm.

Autore: Samuele Gallo
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from common.params import ENHANCED_DIR, IMAGE_SUFFIXES, VIDEO_SUFFIXES

PathLike = Union[str, Path]
# A method reads `src` and writes the improved file to `dst`. It may also take `params` (the settings the user
# chose) and `progress` (a function told how far it is, from 0 to 1): whichever of the two it accepts is passed.
Enhancer = Callable[..., None]


@dataclass
class Method:
    """A way of improving a photo or a video, as the interface sees it."""
    name: str                                            # what `improve(method=...)` takes
    run: Enhancer
    label: str = ""                                      # readable name; the plain name when empty
    description: str = ""
    kind: str = ""                                       # e.g. "deep" or "classical": only shown to the user
    params: Sequence[Dict[str, Any]] = field(default_factory=tuple)
    video: bool = False                                  # whether it can also do videos
    problem: str = ""                                    # why it cannot run here (empty: it can)

    @property
    def title(self) -> str:
        return self.label or self.name

    @property
    def usable(self) -> bool:
        return not self.problem

    def defaults(self) -> Dict[str, Any]:
        return {p["name"]: p.get("default") for p in self.params if "name" in p}


_METHODS: Dict[str, Method] = {}


def register(name: str, enhancer: Enhancer, label: str = "", description: str = "", kind: str = "",
             params: Sequence[Dict[str, Any]] = (), video: bool = False, problem: str = "") -> Method:
    """Adds a way of improving an image or a video. Everything but the name and the function is for the interface."""
    method = Method(name, enhancer, label, description, kind, tuple(params), video, problem)
    _METHODS[name] = method
    return method


def forget_all() -> None:
    """Removes every method (used by the tests, and when the libraries are reloaded)."""
    _METHODS.clear()


def available(video: bool = False) -> List[str]:
    """The methods installed, in the order they were registered (empty: nothing to offer).
    With `video`, only those that can also do videos."""
    return [n for n, m in _METHODS.items() if m.usable and (m.video or not video)]


def methods() -> List[Method]:
    """Every method, the ones that cannot run here included (they carry the reason): the interface shows them
    greyed out instead of hiding them, so the user knows what is missing."""
    return list(_METHODS.values())


def method(name: str = "") -> Method:
    """A method by name, or the first usable one when the name is empty."""
    if name:
        if name not in _METHODS:
            raise LookupError(f"unknown method: {name}")
        return _METHODS[name]
    usable = available()
    if not usable:
        raise LookupError("no image improvement installed")
    return _METHODS[usable[0]]


def is_video(media: PathLike) -> bool:
    return Path(media).suffix.lower() in set(VIDEO_SUFFIXES)


def enhanced_path(media: PathLike) -> Path:
    """Where the improved copy of a file goes: `enhanced/` beside it, with the same name. A video always comes
    back as MP4, so that one changes its extension."""
    media = Path(media)
    name = media.stem + ".mp4" if is_video(media) else media.name
    return media.parent / ENHANCED_DIR / name


def original_path(enhanced: PathLike) -> Path:
    """The inverse: from the improved copy back to its original. The name is the same, but a video may have been
    recorded in another container, so a file with the same stem is taken when the exact name is not there."""
    enhanced = Path(enhanced)
    folder = enhanced.parent.parent
    exact = folder / enhanced.name
    if exact.is_file() or not is_video(enhanced):
        return exact
    same_stem = sorted(p for p in folder.glob(enhanced.stem + ".*") if p.is_file() and is_video(p))
    return same_stem[0] if same_stem else exact


def is_enhanced(media: PathLike) -> bool:
    return Path(media).parent.name == ENHANCED_DIR


def find_enhanced(media: PathLike) -> Optional[Path]:
    """The improved copy of a file, if it has been made."""
    path = enhanced_path(media)
    return path if path.is_file() else None


def can_improve(media: PathLike) -> bool:
    suffix = Path(media).suffix.lower()
    if is_enhanced(media) or suffix not in set(IMAGE_SUFFIXES) | set(VIDEO_SUFFIXES):
        return False
    return bool(available(video=suffix in set(VIDEO_SUFFIXES)))


def improve(media: PathLike, method: str = "", replace: bool = False, params: Optional[Dict[str, Any]] = None,
            progress: Optional[Callable[[float], None]] = None, dest: Optional[PathLike] = None) -> Path:
    """Writes the improved copy of `media` and returns its path. With `replace=False` an existing copy is kept.
    `params` are the settings of the method (its own defaults when left out), and `dest` writes the result
    somewhere else than beside the original (the interface uses it for a preview, or before asking the user
    where the file should end up).
    Raises LookupError if no method is installed, and leaves nothing behind if the method fails."""
    chosen = globals()["method"](method)
    if chosen.problem:
        raise LookupError(chosen.problem)
    media = Path(media)
    if is_video(media) and not chosen.video:
        raise LookupError(f"{chosen.title} does not do videos")
    dest = Path(dest) if dest else enhanced_path(media)
    if dest.is_file() and not replace:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.stem}.part{dest.suffix}")      # the extension is kept: it chooses the format
    try:
        chosen.run(media, tmp, **_extra(chosen.run, params, progress))
        tmp.replace(dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return dest


def _extra(run: Enhancer, params: Optional[Dict[str, Any]], progress: Optional[Callable]) -> Dict[str, Any]:
    """Only what the method is prepared to take: an old one with (src, dst) keeps working."""
    try:
        accepted = inspect.signature(run).parameters
    except (TypeError, ValueError):                             # a builtin: nothing more is passed
        return {}
    out: Dict[str, Any] = {}
    if "params" in accepted:
        out["params"] = params or {}
    if "progress" in accepted and progress is not None:
        out["progress"] = progress
    return out
