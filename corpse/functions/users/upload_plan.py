"""What an upload of photos, stereo photos or videos sends (no Qt): the files with the names they get on the server."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from common.label_store import sidecars
from common.params import AREA_PHOTOS, AREA_STEREO, AREA_VIDEOS, IMAGE_SUFFIXES, STEREO_SIDES, VIDEO_SUFFIXES

Pairs = List[Tuple[Path, str]]


def kind_of(path: Path) -> Optional[str]:
    """The area a media file belongs to: photos or videos (None for any other file)."""
    ext = Path(path).suffix.lower()
    return AREA_PHOTOS if ext in IMAGE_SUFFIXES else AREA_VIDEOS if ext in VIDEO_SUFFIXES else None


def _with_labels(media: Path, remote_dir: str, classes_sent: set) -> Pairs:
    """The media file, its label file and (once per folder) the class names, with their remote names."""
    out: Pairs = [(media, f"{remote_dir}/{media.name}")]
    label, classes = sidecars(media)
    if label is not None:
        out.append((label, f"{remote_dir}/{media.with_suffix('.txt').name}"))      # the label has the media's name
        if classes is not None and remote_dir not in classes_sent:
            classes_sent.add(remote_dir)
            out.append((classes, f"{remote_dir}/classes.txt"))
    return out


def plan_media(files: Sequence[Path], species: str) -> Dict[str, Pairs]:
    """Splits picked files into uploads: {area: [(local, remote)]} for photos and videos. Two files with the same name
    would overwrite each other, so only the first is sent."""
    plan: Dict[str, Pairs] = {}
    seen: Dict[str, set] = {}
    classes_sent: set = set()
    for p in map(Path, files):
        area = kind_of(p)
        if area is None or p.name in seen.setdefault(area, set()):
            continue
        seen[area].add(p.name)
        plan.setdefault(area, []).extend(_with_labels(p, species, classes_sent))
    return plan


def plan_stereo(root: Path, species: str) -> Pairs:
    """A folder holding an `lx` and an `rx` subfolder -> files for <species>/<lx|rx>/<name>. Only photos are sent."""
    root, pairs, classes_sent = Path(root), [], set()
    for side in STEREO_SIDES:
        folder = root / side
        if not folder.is_dir():
            continue
        for p in sorted(folder.iterdir()):
            if p.is_file() and not p.name.startswith(".") and kind_of(p) == AREA_PHOTOS:
                pairs.extend(_with_labels(p, f"{species}/{side}", classes_sent))
    return pairs


def has_stereo_folders(root: Path) -> bool:
    return all((Path(root) / s).is_dir() for s in STEREO_SIDES)
