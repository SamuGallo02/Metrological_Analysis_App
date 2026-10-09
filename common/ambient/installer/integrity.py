"""
Integrity check of the virtual environment (standard library only).

Every package installed by pip lists its files in `<name>-<version>.dist-info/RECORD`, with size and
SHA-256 of each one. Comparing the disk with that list finds truncated, corrupted or deleted files
(e.g. a `torch_cuda.dll` cut short by a full disk) without importing anything.

  quick scan: existence + size of every file (only `stat`, about a second)
  deep scan:  also the SHA-256 of every file (reads all the data, tens of seconds)
"""
from __future__ import annotations

import base64
import csv
import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

_SKIP_SUFFIXES = (".pyc", ".pyo")
_CHUNK = 1 << 20


@dataclass
class Damage:
    name: str
    version: str
    files: List[str] = field(default_factory=list)      # relative paths missing or different from the RECORD

    def __str__(self) -> str:
        more = f" (+{len(self.files) - 3} more)" if len(self.files) > 3 else ""
        return f"{self.name} {self.version}: {', '.join(self.files[:3])}{more}"


def site_packages(venv: Path) -> List[Path]:
    """The site-packages folders of a virtual environment (Windows and POSIX layouts)."""
    found = [venv / "Lib" / "site-packages"]
    lib = venv / "lib"
    if lib.is_dir():
        found += sorted(lib.glob("python3*/site-packages"))
    return [p for p in found if p.is_dir()]


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            buf = f.read(_CHUNK)
            if not buf:
                break
            h.update(buf)
    return base64.urlsafe_b64encode(h.digest()).rstrip(b"=").decode("ascii")


def _split_dist(folder: str):
    stem = folder[:-len(".dist-info")]
    name, _, version = stem.partition("-")
    return name.replace("_", "-"), version


def check_dist(dist_info: Path, deep: bool = False) -> Optional[Damage]:
    """Compares one package with its RECORD. Returns the damage, or None if everything is in place."""
    record = dist_info / "RECORD"
    name, version = _split_dist(dist_info.name)
    if not record.is_file():
        return None                                     # not installed by pip (or editable): nothing to compare
    base = dist_info.parent
    bad: List[str] = []
    try:
        with open(record, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
    except (OSError, UnicodeDecodeError):
        return Damage(name, version, ["RECORD"])
    for row in rows:
        if len(row) < 3 or not row[0] or not row[2]:    # the RECORD itself has no size/hash
            continue
        rel, algo_hash, size = row[0], row[1], row[2]
        if rel.startswith("..") or rel.endswith(_SKIP_SUFFIXES) or "__pycache__" in rel:
            continue                                    # scripts outside site-packages, bytecode
        path = base / rel
        try:
            if path.stat().st_size != int(size):
                bad.append(rel)
                continue
            if deep and algo_hash.startswith("sha256=") and _digest(path) != algo_hash[7:]:
                bad.append(rel)
        except (OSError, ValueError):
            bad.append(rel)
    return Damage(name, version, bad) if bad else None


def scan(venv: Path, deep: bool = False, progress: Optional[Callable[[int, int], None]] = None) -> Dict[str, Damage]:
    """Checks every package of the environment. Returns {package: Damage} for the damaged ones."""
    infos = [d for sp in site_packages(venv) for d in sorted(sp.glob("*.dist-info"))]
    damaged: Dict[str, Damage] = {}
    for i, info in enumerate(infos, 1):
        d = check_dist(info, deep)
        if d:
            damaged[d.name.lower()] = d
        if progress:
            progress(i, len(infos))
    return damaged


def current_venv() -> Optional[Path]:
    """The virtual environment this interpreter runs in (None for a system Python)."""
    return Path(sys.prefix) if sys.prefix != getattr(sys, "base_prefix", sys.prefix) else None


def torch_index(version: str) -> Optional[str]:
    """PyTorch index of a build from its version tag ('2.6.0+cu126' -> .../whl/cu126)."""
    from . import plan
    return plan.PYTORCH_INDEX + version.split("+", 1)[1] if "+" in version else None


def venv_is_project(venv: Optional[Path], project_venv: Path) -> bool:
    try:
        return venv is not None and os.path.samefile(venv, project_venv)
    except OSError:
        return False


def launch_repair(project_root: Path, os_name: str, deep: bool = False) -> bool:
    """Starts the repair in a detached, windowless process that waits for this app to close, fixes the
    damaged packages and reopens the app. Returns True if the process started (the caller must quit).
    Used only when the repair cannot run inside the app (the damaged package is Qt itself)."""
    from common.params import DETACHED_HIDDEN

    from . import state
    py = state.venv_python(os_name)
    if not py.exists():
        py = Path(sys.executable)
    cmd = [str(py), "-m", "common.ambient.installer", "--os", os_name, "--repair", "--yes", "--relaunch",
           "--wait-pid", str(os.getpid())] + (["--deep"] if deep else [])
    try:
        subprocess.Popen(cmd, cwd=str(project_root), **DETACHED_HIDDEN)
        return True
    except OSError:
        return False


def startup_check(deep: bool = False) -> Dict[str, Damage]:
    """Quick check of the project's virtual environment before the app loads its libraries.
    Returns the damaged packages ({} if all is well, or if the app does not run in the project venv,
    e.g. during development, or if the check itself fails: it must never block the app)."""
    from . import state
    from .sysinfo import detect_os
    venv = state.venv_dir(detect_os())
    if not venv_is_project(current_venv(), venv):
        return {}
    try:
        return scan(venv, deep)
    except Exception:
        return {}


def touches_qt(damaged: Dict[str, Damage]) -> bool:
    """True if Qt itself is damaged: the app cannot repair it while it is running (locked files)."""
    return any(n.startswith(("pyside6", "shiboken6")) for n in damaged)
