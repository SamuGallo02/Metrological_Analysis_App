"""Reading the code from GitHub: archives (zip) and single files, always pinned to a commit."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Dict, Optional
from urllib.parse import quote

from . import config

Progress = Optional[Callable[[int, int], None]]
_SHA = re.compile(r"^[0-9a-f]{40}$")


class SourceError(Exception):
    """Network or archive problem, with a message fit for the user."""


def http_get(url: str, timeout: float = config.HTTP_TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "AnalisiMetrologica-updater",
                                               "Accept": "application/vnd.github+json, */*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as e:                                  # noqa: BLE001
        raise SourceError(f"{url}: {e}") from e


def get_json(path: str, timeout: float = config.HTTP_TIMEOUT):
    return json.loads(http_get(config.api() + path, timeout).decode("utf-8"))


def archive_url(ref: str) -> str:
    return f"{config.web()}/{config.repo()}/archive/{ref}.zip"


def download_archive(ref: str, dest: Path, progress: Progress = None, timeout: float = config.HTTP_TIMEOUT) -> Path:
    """Downloads the zip of a commit/tag/branch into `dest`."""
    req = urllib.request.Request(archive_url(ref), headers={"User-Agent": "AnalisiMetrologica-updater"})
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as out:
            total, done = int(r.headers.get("Content-Length") or 0), 0
            while True:
                chunk = r.read(1 << 18)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except Exception as e:                                  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise SourceError(f"{archive_url(ref)}: {e}") from e
    return dest


def fetch_file(sha: str, rel: str, timeout: float = config.HTTP_TIMEOUT) -> bytes:
    """One file of the repository at an exact commit (what the manifest was computed on)."""
    return http_get(f"{config.raw()}/{config.repo()}/{sha}/{quote(rel)}", timeout)


def zip_commit(z: zipfile.ZipFile) -> str:
    """GitHub stores the commit SHA of the archive in the zip comment ('' if it is not there)."""
    c = (z.comment or b"").decode("ascii", "ignore").strip().lower()
    return c if _SHA.match(c) else ""


def zip_files(z: zipfile.ZipFile) -> Dict[str, zipfile.ZipInfo]:
    """Files of the archive, as {path relative to the project: ZipInfo} (the top folder is removed)."""
    names = [i.filename for i in z.infolist() if i.filename and not i.filename.startswith("__MACOSX")]
    tops = {n.split("/", 1)[0] for n in names}
    strip = (next(iter(tops)) + "/") if len(tops) == 1 and any("/" in n for n in names) else ""
    out: Dict[str, zipfile.ZipInfo] = {}
    for i in z.infolist():
        n = i.filename
        if i.is_dir() or n.startswith("__MACOSX") or not n.startswith(strip):
            continue
        rel = n[len(strip):]
        if rel and ".." not in rel.split("/") and not rel.startswith("/"):    # protection against malicious paths
            out[rel] = i
    return out


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def open_zip(path: Path) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise SourceError(f"Corrupt archive: {e}") from e


def zip_from_bytes(data: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(data))


# ---- interchangeable sources ----------------------------------------------------
class UpdateSource:
    """Where the code of the user edition is read from. GitHub today; later the project's own server, which will
    publish the same three things: which version is the latest, its archive, and single files of an exact version.
    The updater only talks to this interface, so changing the source does not touch the rest."""

    name = ""

    def latest(self, timeout: float = config.HTTP_TIMEOUT):
        """The newest published version (a `versions.Version`)."""
        raise NotImplementedError

    def download_archive(self, ref: str, dest: Path, progress: Progress = None,
                         timeout: float = config.HTTP_TIMEOUT) -> Path:
        """The archive (zip) of a version into `dest`."""
        raise NotImplementedError

    def fetch_file(self, sha: str, rel: str, timeout: float = config.HTTP_TIMEOUT) -> bytes:
        """One file of an exact version (used to repair only what is damaged)."""
        raise NotImplementedError


class GitHubSource(UpdateSource):
    name = "github"

    def latest(self, timeout: float = config.HTTP_TIMEOUT):
        from .versions import Version
        repo = config.repo()
        tag, published = "", ""
        try:
            rel = get_json(f"/repos/{repo}/releases/latest", timeout)
            tag, published = str(rel.get("tag_name") or ""), str(rel.get("published_at") or "")
        except SourceError:
            pass                                          # no releases (404) or not reachable: look at the branch
        ref = tag or config.BRANCH
        commit = get_json(f"/repos/{repo}/commits/{ref}", timeout)
        sha = str(commit.get("sha") or "")
        if not sha:
            raise SourceError("GitHub did not return a commit.")
        if not published:
            published = str(((commit.get("commit") or {}).get("committer") or {}).get("date") or "")
        return Version(sha=sha, label=tag or f"{config.BRANCH}@{sha[:7]}", published=published)

    def download_archive(self, ref, dest, progress=None, timeout=config.HTTP_TIMEOUT):
        return download_archive(ref, dest, progress, timeout)

    def fetch_file(self, sha, rel, timeout=config.HTTP_TIMEOUT):
        return fetch_file(sha, rel, timeout)


_FACTORIES: Dict[str, Callable[[], UpdateSource]] = {"github": GitHubSource}


def register(name: str, factory: Callable[[], UpdateSource]) -> None:
    """Adds a source (the server one will be registered here when it exists)."""
    _FACTORIES[name] = factory


def current(name: Optional[str] = None) -> UpdateSource:
    """The source in use: `name`, else the AM_UPDATE_SOURCE variable, else `config.DEFAULT_SOURCE`."""
    wanted = name or os.environ.get("AM_UPDATE_SOURCE") or config.DEFAULT_SOURCE
    factory = _FACTORIES.get(wanted)
    if factory is None:
        raise SourceError(f"Unknown update source: {wanted}")
    return factory()
