"""Update preferences (librery/.update_prefs.json): mode, last automatic check, version to skip."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict

from . import config


def _path(root: Path) -> Path:
    return Path(root) / config.PREFS_FILE


def load(root: Path) -> Dict[str, Any]:
    try:
        d = json.loads(_path(root).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save(root: Path, **changes: Any) -> Dict[str, Any]:
    d = load(root)
    d.update(changes)
    p = _path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
    os.replace(tmp, p)
    return d


def mode(root: Path) -> str:
    m = load(root).get("mode", config.DEFAULT_MODE)
    return m if m in config.MODES else config.DEFAULT_MODE


def check_due(root: Path) -> bool:
    return time.time() - float(load(root).get("last_check", 0) or 0) >= config.CHECK_EVERY


def mark_checked(root: Path) -> None:
    save(root, last_check=int(time.time()))
