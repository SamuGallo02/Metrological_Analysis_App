"""Record of the installed code and its verification.

librery/.code_version.json = {"repo", "sha", "label", "installed_at", "os",
                              "files": {"<path>": {"size": n, "sha256": "..."}}}
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import config


@dataclass
class Problem:
    rel: str
    kind: str                       # "missing" | "size" | "hash"

    def __str__(self) -> str:
        return {"missing": "mancante", "size": "incompleto", "hash": "danneggiato"}[self.kind] + f": {self.rel}"


def version_path(root: Path) -> Path:
    return Path(root) / config.VERSION_FILE


def load(root: Path) -> Optional[dict]:
    try:
        data = json.loads(version_path(root).read_text(encoding="utf-8"))
        return data if isinstance(data.get("files"), dict) else None
    except (OSError, ValueError):
        return None


def save(root: Path, data: dict) -> None:
    p = version_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, p)


def new_record(sha: str, label: str, os_name: str, files: Dict[str, dict]) -> dict:
    return {"repo": config.repo(), "sha": sha, "label": label, "os": os_name,
            "installed_at": int(time.time()), "files": files}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(root: Path, deep: bool = False, record: Optional[dict] = None,
           progress: Optional[Callable[[int, int], None]] = None) -> List[Problem]:
    """Files of the installation that are missing or damaged.
    Quick (default): existence and size, which catches missing and truncated files in milliseconds.
    Deep: also the SHA-256 of every file."""
    record = record if record is not None else load(root)
    if not record:
        return []
    root, files, out = Path(root), record["files"], []
    for n, (rel, meta) in enumerate(sorted(files.items()), 1):
        p = root / rel
        try:
            size = p.stat().st_size
        except OSError:
            out.append(Problem(rel, "missing"))
            continue
        if size != meta["size"]:
            out.append(Problem(rel, "size"))
        elif deep and sha256_file(p) != meta["sha256"]:
            out.append(Problem(rel, "hash"))
        if progress:
            progress(n, len(files))
    return out
