"""Logging to console + rotating file (<data>/logs/server.log)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)s %(message)s"


def setup(data_dir: Path, level: int = logging.INFO, max_bytes: int = 5 << 20, backups: int = 5) -> Path:
    logs = Path(data_dir) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    for h in (logging.StreamHandler(), RotatingFileHandler(logs / "server.log", maxBytes=max_bytes,
                                                            backupCount=backups, encoding="utf-8")):
        h.setFormatter(logging.Formatter(FORMAT))
        root.addHandler(h)
    return logs / "server.log"
