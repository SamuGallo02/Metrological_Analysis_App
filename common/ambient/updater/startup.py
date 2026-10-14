"""What main.py does before importing the application: verify the code, repair it, install updates (auto mode)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

from common.params import NO_WINDOW

from . import apply, config, manifest, prefs, source, versions


def run(root: Path, os_name: str, deep: bool = False, allow_update: bool = True, log=print) -> str:
    """Returns "skipped" (git working copy or code not installed by the installer), "ok", "repaired",
    "failed" (some files could not be restored: no network?) or "updated" (a new version was installed:
    the caller must restart)."""
    root = Path(root)
    record = manifest.load(root)
    if record is None or versions.is_dev_checkout(root):
        return "skipped"
    outcome = "ok"
    problems = manifest.verify(root, deep, record)
    if problems:
        log("[WARNING] Damaged or missing files:\n  " + "\n  ".join(map(str, problems[:12])))
        fixed, failed = apply.repair(root, problems, record)
        if failed:
            log("[ERROR] Could not restore: " + ", ".join(failed[:8]) + " (check the internet connection).")
            return "failed"
        log(f"[OK] Restored {len(fixed)} file(s).")
        outcome = "repaired"
    if allow_update and prefs.mode(root) == "auto" and prefs.check_due(root):
        prefs.mark_checked(root)
        try:
            latest = versions.latest(config.QUICK_TIMEOUT)
            if latest.sha != record.get("sha"):
                log(f"[..] Installing the new version {latest.label} ...")
                result = apply.update(root, latest, os_name)
                if result["requirements_changed"]:
                    install_components(root, os_name)
                return "updated"
        except (source.SourceError, OSError) as e:           # never block the start because of the network
            log(f"[INFO] Update check skipped: {e}")
    return outcome


def install_components(root: Path, os_name: str, line=None) -> int:
    """After an update that changes the library lists: installs only what is missing (the usual installer)."""
    cmd = [sys.executable, "-m", "common.ambient.installer", "--os", os_name, "--component", "core", "--yes"]
    proc = subprocess.Popen(cmd, cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", **NO_WINDOW)
    for ln in proc.stdout:
        if line:
            line(ln.rstrip())
    return proc.wait()
