"""Which version is installed and which is the latest one on GitHub."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import config, manifest, source


@dataclass
class Version:
    sha: str
    label: str                      # "v1.2" for a release, "main@abc1234" for the branch head
    published: str = ""             # date as given by GitHub


def latest(timeout: float = config.HTTP_TIMEOUT) -> Version:
    """Newest published version of the user edition, from the update source in use (a release if there are any,
    otherwise the head of the main branch, for GitHub)."""
    return source.current().latest(timeout)


def installed(root: Path) -> Optional[dict]:
    return manifest.load(root)


def installed_label(root: Path) -> str:
    rec = installed(root)
    return rec["label"] if rec else ""


def is_dev_checkout(root: Path) -> bool:
    """A git working copy updates with git: the updater leaves it alone."""
    return (Path(root) / ".git").exists()
