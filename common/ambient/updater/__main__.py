"""python -m common.ambient.updater  status | check | update | repair | mode"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from common.params import PROGRESS_PREFIX

from .. import installer as _installer           # noqa: F401  (package must be importable)
from ..installer.sysinfo import detect_os
from . import apply, config, manifest, prefs, source, startup, versions

ROOT = Path(__file__).resolve().parents[3]
EXIT_UPDATE_AVAILABLE = 10


def _progress(pct: float, text: str) -> None:
    print(f"{PROGRESS_PREFIX} {pct:.0f} {text}", flush=True)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="updater", description="Code integrity and updates")
    ap.add_argument("--root", default=str(ROOT), help="project folder (default: this one)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("--json", action="store_true")
    c = sub.add_parser("check", help="is there a newer version? exit code 10 if yes")
    c.add_argument("--json", action="store_true")
    sub.add_parser("update", help="install the latest version (only the changed files)")
    r = sub.add_parser("repair", help="download again only the missing or damaged files")
    r.add_argument("--deep", action="store_true", help="also compare the SHA-256 of every file")
    m = sub.add_parser("mode")
    m.add_argument("value", choices=config.MODES)
    a = ap.parse_args(argv)
    root = Path(a.root)
    os_name = detect_os()
    rec = manifest.load(root)

    try:
        if a.cmd == "status":
            d = {"installed": (rec or {}).get("label", ""), "sha": (rec or {}).get("sha", ""),
                 "mode": prefs.mode(root), "dev": versions.is_dev_checkout(root), "recorded": rec is not None}
            print(json.dumps(d) if a.json else "\n".join(f"{k}: {v}" for k, v in d.items()))
            return 0
        if a.cmd == "mode":
            prefs.save(root, mode=a.value)
            print(f"Update mode: {a.value}")
            return 0
        if a.cmd == "check":
            latest = versions.latest()
            prefs.mark_checked(root)
            current = (rec or {}).get("sha", "")
            newer = latest.sha != current
            if a.json:
                print(json.dumps({"available": newer, "latest": latest.label, "sha": latest.sha,
                                  "installed": (rec or {}).get("label", "")}))
            else:
                print(f"Installed: {(rec or {}).get('label') or 'unknown'}\nLatest   : {latest.label}\n"
                      + ("A new version is available." if newer else "You have the latest version."))
            return EXIT_UPDATE_AVAILABLE if newer else 0
        if a.cmd == "repair":
            if rec is None:
                print("No record of the installed code: use `update` to align this installation with GitHub.")
                return 1
            problems = manifest.verify(root, a.deep, rec, lambda n, t: _progress(5 * n / t, "check"))
            if not problems:
                print("All files are fine.")
                return 0
            print("\n".join(map(str, problems)))
            fixed, failed = apply.repair(root, problems, rec, _progress)
            print(f"Restored {len(fixed)} file(s)." + (f" Failed: {', '.join(failed)}" if failed else ""))
            return 1 if failed else 0
        if a.cmd == "update":
            _progress(1, "check")
            latest = versions.latest()
            res = apply.update(root, latest, os_name, _progress)
            print(f"Updated to {latest.label}: {len(res['updated'])} changed, {len(res['added'])} new, "
                  f"{len(res['removed'])} removed.")
            if res["requirements_changed"]:
                print("The library lists changed: installing what is missing...")
                rc = startup.install_components(root, os_name, print)
                if rc != 0:
                    print("Library installation did not complete: run the installer again.")
                    return 1
            _progress(100, "")
            return 0
    except (source.SourceError, OSError) as e:
        print(f"Error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
