"""Backup, restore and rotation of the server database (and, optionally, of the data folders)."""
from __future__ import annotations

import shutil
import sqlite3
import tarfile
import time
from pathlib import Path
from typing import List, Optional

PREFIX = "server-"


class BackupError(Exception):
    """Error shown on the console by the backup commands (not translated: it never reaches the app)."""


def _stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def backup_db(db_file: Path, dest_dir: Path) -> Path:
    """Consistent copy of the live database (SQLite online backup: the server can keep running)."""
    db_file, dest_dir = Path(db_file), Path(dest_dir)
    if not db_file.exists():
        raise BackupError(f"Database not found: {db_file}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{PREFIX}{_stamp()}.db"
    src, dst = sqlite3.connect(str(db_file)), sqlite3.connect(str(out))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return out


def backup_files(data_dir: Path, dest_dir: Path) -> Path:
    """Compressed archive of the whole data folder (database included, backups folder excluded)."""
    data_dir, dest_dir = Path(data_dir), Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{PREFIX}{_stamp()}-data.tar.gz"
    skip = dest_dir.resolve()
    with tarfile.open(out, "w:gz") as tar:
        for p in sorted(data_dir.iterdir()):
            if p.resolve() == skip or p.name in ("logs", ".uploads_tmp"):
                continue
            tar.add(p, arcname=p.name)
    return out


def list_backups(dest_dir: Path) -> List[Path]:
    d = Path(dest_dir)
    return sorted(d.glob(PREFIX + "*"), key=lambda p: p.stat().st_mtime, reverse=True) if d.is_dir() else []


def prune(dest_dir: Path, keep: int) -> List[Path]:
    """Keeps the newest `keep` backups, removes the others. Returns the removed files."""
    old = list_backups(dest_dir)[max(keep, 1):]
    for p in old:
        p.unlink(missing_ok=True)
    return old


def restore_db(backup: Path, db_file: Path, server_running: bool = False) -> Optional[Path]:
    """Replaces the database with a backup. The current one is kept as <name>.before-restore."""
    backup, db_file = Path(backup), Path(db_file)
    if server_running:
        raise BackupError("Stop the server before restoring a backup.")
    try:
        con = sqlite3.connect(str(backup))
        ok = con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        con.close()
    except sqlite3.DatabaseError:
        ok = False
    if not ok:
        raise BackupError("The backup file is not a valid database.")
    saved = None
    if db_file.exists():
        saved = db_file.with_name(db_file.name + ".before-restore")
        shutil.copy2(db_file, saved)
    for ext in ("-wal", "-shm"):                                   # stale journals would corrupt the restored file
        db_file.with_name(db_file.name + ext).unlink(missing_ok=True)
    shutil.copy2(backup, db_file)
    return saved
