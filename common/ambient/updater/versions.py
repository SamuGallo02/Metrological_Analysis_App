"""Which version is installed and which is the latest one on GitHub."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import config, manifest
from .source import SourceError, get_json


@dataclass
class Version:
    sha: str
    label: str                      # "v1.2" for a release, "main@abc1234" for the branch head
    published: str = ""             # date as given by GitHub


def latest(timeout: float = config.HTTP_TIMEOUT) -> Version:
    """Newest published version: the latest GitHub release if the repository has releases (a version is
    'launched' when a release is published), otherwise the head of the main branch."""
    repo = config.repo()
    tag, published = "", ""
    try:
        rel = get_json(f"/repos/{repo}/releases/latest", timeout)
        tag, published = str(rel.get("tag_name") or ""), str(rel.get("published_at") or "")
    except SourceError:
        pass                                              # no releases (404) or not reachable: look at the branch
    ref = tag or config.BRANCH
    commit = get_json(f"/repos/{repo}/commits/{ref}", timeout)
    sha = str(commit.get("sha") or "")
    if not sha:
        raise SourceError("GitHub did not return a commit.")
    if not published:
        published = str(((commit.get("commit") or {}).get("committer") or {}).get("date") or "")
    return Version(sha=sha, label=tag or f"{config.BRANCH}@{sha[:7]}", published=published)


def installed(root: Path) -> Optional[dict]:
    return manifest.load(root)


def installed_label(root: Path) -> str:
    rec = installed(root)
    return rec["label"] if rec else ""


def is_dev_checkout(root: Path) -> bool:
    """A git working copy updates with git: the updater leaves it alone."""
    return (Path(root) / ".git").exists()
