"""Repair (only the damaged files) and update (only the changed files) of the installed code."""
from __future__ import annotations

import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from . import config, manifest, source
from .versions import Version

Progress = Optional[Callable[[float, str], None]]


def _say(progress: Progress, pct: float, text: str) -> None:
    if progress:
        progress(pct, text)


def _inside(root: Path, rel: str) -> Path:
    target = (root / rel).resolve()
    if root.resolve() not in target.parents:
        raise source.SourceError(f"Path outside the project: {rel}")
    return target


def write_file(root: Path, rel: str, data: bytes, executable: bool = False) -> None:
    """Atomic write: the old file stays intact until the new one is complete."""
    target = _inside(Path(root), rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".am_tmp")
    tmp.write_bytes(data)
    if executable or rel.endswith((".sh", ".command")):
        os.chmod(tmp, 0o755)
    os.replace(tmp, target)


# ---- repair --------------------------------------------------------------------
def repair(root: Path, problems: List[manifest.Problem], record: dict, progress: Progress = None
           ) -> Tuple[List[str], List[str]]:
    """Downloads again ONLY the files in `problems`, exactly as they were installed (same commit, same SHA-256).
    Returns (repaired, failed)."""
    root, files, sha = Path(root), record["files"], record.get("sha", "")
    todo = [p.rel for p in problems if p.rel in files]
    fixed: List[str] = []
    done = [0]

    def one(rel: str) -> Optional[str]:
        try:
            data = source.fetch_file(sha, rel)
            if source.sha256_bytes(data) != files[rel]["sha256"]:
                return None
            write_file(root, rel, data)
            return rel
        except (source.SourceError, OSError):
            return None
        finally:
            done[0] += 1
            _say(progress, 5 + 80 * done[0] / max(len(todo), 1), f"{done[0]}/{len(todo)}")

    if sha:                                              # single files at the installed commit
        with ThreadPoolExecutor(max_workers=6) as ex:
            fixed = [r for r in ex.map(one, todo) if r]
    failed = [r for r in todo if r not in fixed]
    if failed:                                           # fallback: the archive, taking only the missing files
        _say(progress, 88, "archive")
        tmpdir = Path(tempfile.mkdtemp(prefix="am_repair_"))
        try:
            z = source.open_zip(source.download_archive(sha or config.BRANCH, tmpdir / "src.zip"))
            members = source.zip_files(z)
            for rel in list(failed):
                info = members.get(rel)
                if info is None:
                    continue
                data = z.read(info)
                if source.sha256_bytes(data) == files[rel]["sha256"]:
                    write_file(root, rel, data)
                    fixed.append(rel)
                    failed.remove(rel)
            z.close()
        except (source.SourceError, OSError):
            pass
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    _say(progress, 100, "")
    return fixed, failed


# ---- update --------------------------------------------------------------------
def update(root: Path, version: Version, os_name: str, progress: Progress = None) -> Dict[str, object]:
    """Brings the installation to `version`, writing only the files that differ (or are new) and removing the
    ones that no longer exist. User data (datasets, librery, models) is not part of the code and is never touched.
    Returns {"updated": [...], "added": [...], "removed": [...], "requirements_changed": bool, "sha": ...}."""
    root = Path(root)
    tmpdir = Path(tempfile.mkdtemp(prefix="am_update_"))
    try:
        _say(progress, 2, "download")
        z = source.open_zip(source.download_archive(
            version.sha, tmpdir / "src.zip", lambda d, t: _say(progress, 2 + 40 * d / t if t else 20, "download")))
        sha = source.zip_commit(z) or version.sha
        members = {r: i for r, i in source.zip_files(z).items() if config.wanted(r, os_name)}
        if not any(r == "main.py" for r in members):
            raise source.SourceError("The archive does not contain the application.")
        old = manifest.load(root)
        old_files = (old or {}).get("files", {})
        new_files: Dict[str, dict] = {}
        updated: List[str] = []
        added: List[str] = []
        total = len(members)
        for n, (rel, info) in enumerate(sorted(members.items()), 1):
            data = z.read(info)
            h = source.sha256_bytes(data)
            new_files[rel] = {"size": len(data), "sha256": h}
            target = root / rel
            same = target.is_file() and target.stat().st_size == len(data) and manifest.sha256_file(target) == h
            if not same:
                write_file(root, rel, data, executable=bool((info.external_attr >> 16) & 0o111))
                (updated if target.exists() and rel in old_files else added).append(rel)
            _say(progress, 45 + 45 * n / total, f"{n}/{total}")
        removed = [r for r in old_files if r not in new_files]
        for rel in removed:
            try:
                p = _inside(root, rel)
                p.unlink(missing_ok=True)
                _prune_empty(p.parent, root)
            except (OSError, source.SourceError):
                pass
        z.close()
        manifest.save(root, manifest.new_record(sha, version.label, os_name, new_files))
        changed = updated + added + removed
        req = any(r.startswith(config.REQUIREMENTS_DIR + "/") for r in changed)
        _say(progress, 92, "done")
        return {"updated": updated, "added": added, "removed": removed, "requirements_changed": req, "sha": sha}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _prune_empty(folder: Path, root: Path) -> None:
    root = root.resolve()
    while folder.resolve() != root and folder.is_dir() and not any(folder.iterdir()):
        try:
            folder.rmdir()
        except OSError:
            break
        folder = folder.parent
