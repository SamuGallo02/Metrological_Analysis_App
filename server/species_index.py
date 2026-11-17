"""Which species the photos and the videos of the server belong to.

The same rule as on the computer of the user: the species of a file are the classes of its labels, so a photo of
two animals is under both without being copied anywhere. The files stay where the review put them - one folder
per upload, named after the species that was declared - and this only offers another way of looking at them.

The server has no image library and reads nothing but text: the labels beside a media file (`name.txt`) and the
class names of its folder (`classes.txt`). What has been read is remembered until the file changes, because a
library can hold thousands of photos and a view must not re-read them all every time.

Autore: Samuele Gallo
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

from common.params import IMAGE_SUFFIXES, VIDEO_SUFFIXES

from .media_tree import CLASSES_FILE

LABEL_SUFFIX = ".txt"
MEDIA_SUFFIXES = {s.lower() for s in tuple(IMAGE_SUFFIXES) + tuple(VIDEO_SUFFIXES)}
UNNAMED = ""                                     # the files that carry no label yet
MAX_FILES = 20000                                # a view is built out of this many files at most


def _class_numbers(text: str) -> List[int]:
    """The class of every label line (the first number); a line that is not a label is skipped."""
    out = []
    for line in text.splitlines():
        head = line.strip().split(" ")
        if not head or not head[0]:
            continue
        if head[0].isdigit() and len(head) >= 5:               # photo: cls x y w h (or a polygon)
            out.append(int(head[0]))
    return out


def _video_class_numbers(text: str) -> List[int]:
    out = []
    for line in text.splitlines():
        parts = line.strip().split(" ")
        if len(parts) >= 6 and parts[0].isdigit() and parts[1].isdigit():
            out.append(int(parts[1]))
    return out


class SpeciesIndex:
    """Reads the labels of a folder tree and says which species each file carries."""

    def __init__(self) -> None:
        self._files: Dict[str, Tuple[float, int, List[str]]] = {}      # media -> (mtime, size, species)
        self._classes: Dict[str, Tuple[float, List[str]]] = {}         # folder -> (mtime, class names)

    def forget(self, path: Optional[Path] = None) -> None:
        if path is None:
            self._files.clear()
            self._classes.clear()
            return
        self._files.pop(str(path), None)
        self._classes.pop(str(Path(path).parent), None)

    def classes_of(self, folder: Path) -> List[str]:
        """The class names of a folder (`classes.txt`), empty when it has none."""
        names_file = folder / CLASSES_FILE
        try:
            mtime = names_file.stat().st_mtime
        except OSError:
            return []
        known = self._classes.get(str(folder))
        if known and known[0] == mtime:
            return known[1]
        try:
            names = [line.strip() for line in names_file.read_text(encoding="utf-8", errors="replace").splitlines()
                     if line.strip()]
        except OSError:
            names = []
        self._classes[str(folder)] = (mtime, names)
        return names

    def species_of(self, media: Path) -> List[str]:
        """The species of one media file, in the order its classes appear."""
        try:
            st = media.stat()
        except OSError:
            return []
        label = media.with_suffix(LABEL_SUFFIX)
        try:
            label_st = label.stat()
        except OSError:
            return []
        stamp = max(st.st_mtime, label_st.st_mtime)
        known = self._files.get(str(media))
        if known and known[0] == stamp and known[1] == st.st_size:
            return known[2]
        try:
            text = label.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        numbers = _video_class_numbers(text) if media.suffix.lower() in {s.lower() for s in tuple(VIDEO_SUFFIXES)} \
            else _class_numbers(text)
        names = self.classes_of(media.parent)
        found: List[str] = []
        for cls in numbers:
            name = names[cls] if 0 <= cls < len(names) else str(cls)
            if name not in found:
                found.append(name)
        self._files[str(media)] = (stamp, st.st_size, found)
        return found

    def build(self, root: Path, skip: Tuple[str, ...] = ()) -> Dict[str, List[Dict[str, Any]]]:
        """{species: [file, ...]} of a whole area. A file with two species is in both lists, once each; one with
        no labels is under UNNAMED. Every entry carries what a view needs: path inside the area, size, date."""
        out: Dict[str, List[Dict[str, Any]]] = {}
        if not root.is_dir():
            return out
        seen = 0
        for path in sorted(root.rglob("*")):
            if seen >= MAX_FILES:
                break
            if not path.is_file() or path.suffix.lower() not in MEDIA_SUFFIXES:
                continue
            rel = PurePosixPath(path.relative_to(root).as_posix())
            if skip and rel.parts and rel.parts[0] in skip:
                continue
            seen += 1
            try:
                st = path.stat()
            except OSError:
                continue
            entry = {"path": str(rel), "name": path.name, "type": "file", "size": st.st_size, "mtime": st.st_mtime}
            for name in self.species_of(path) or [UNNAMED]:
                out.setdefault(name, []).append(entry)
        return out
