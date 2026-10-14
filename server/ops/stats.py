"""Server statistics (for `python -m server status` and /api/stats)."""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any, Dict

from .. import params
from ..db import Database


def folder_size(path: Path) -> int:
    total = 0
    for p in Path(path).rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def collect(db: Database, data_dir: Path, started: float = 0.0, requests: int = 0) -> Dict[str, Any]:
    data_dir = Path(data_dir)
    now = time.time()
    with db._c() as c:
        users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        admins = c.execute("SELECT COUNT(*) FROM users WHERE role=? AND active=1", ("server",)).fetchone()[0]
        sessions = c.execute("SELECT COUNT(*) FROM tokens WHERE expires>?", (now,)).fetchone()[0]
        last_day = c.execute("SELECT COUNT(*) FROM events WHERE ts>?", (now - 86400,)).fetchone()[0]
        logins = c.execute("SELECT COUNT(*) FROM events WHERE action='login' AND ts>?", (now - 86400,)).fetchone()[0]
    usage = shutil.disk_usage(data_dir if data_dir.exists() else data_dir.parent)
    areas = {a: folder_size(data_dir / d) for a, d in params.AREA_DIRS.items() if (data_dir / d).is_dir()}
    return {"api": params.API_VERSION, "uptime": int(now - started) if started else None, "requests": requests,
            "users": users, "admins": admins, "sessions": sessions, "events_24h": last_day, "logins_24h": logins,
            "db_bytes": db.path.stat().st_size if db.path.exists() else 0, "areas": areas,
            "disk_free": usage.free, "disk_total": usage.total}


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)
