"""Where the code comes from and which files belong to an installation. A single place to edit."""
from __future__ import annotations

import os
from typing import Optional

REPO = "nautilus-unipd/Metrological_Analysis_App"
BRANCH = "main"
DEFAULT_SOURCE = "github"                  # where the code comes from; the project's own server will be added
DEFAULT_MODE = "ask"                       # "ask" (propose), "auto" (install at startup) or "off"
MODES = ("ask", "auto", "off")
CHECK_EVERY = 24 * 3600                    # seconds between two automatic checks
HTTP_TIMEOUT = 30                          # seconds
QUICK_TIMEOUT = 4                          # automatic checks must never hold the app back

# What the "user edition" (the one downloaded from the site) does NOT contain: the server, its deployment kit, the
# tests, the developer tools and the administrator screens. Same lists as the downloadable installer (a test checks it).
SKIP_DIRS = {"server", "server_data", "tests", "docs", "site", "deploy", ".github", "tools"}
SKIP_FILES = {"corpse/gui/users/admin.py", ".dockerignore", ".gitattributes", ".gitignore"}
LAUNCHER_DIR = "common/launchers"
LAUNCHERS = {"windows": "AnalisiMetrologica.vbs", "macos": "AvviaAnalisiMetrologica.command",
             "linux": "AvviaAnalisiMetrologica.sh"}
REQUIREMENTS_DIR = "common/ambient/requirements"
VERSION_FILE = "librery/.code_version.json"        # inside the project: git-ignored with the rest of librery/
PREFS_FILE = "librery/.update_prefs.json"


def api() -> str:                          # overridable (tests use a local fake GitHub)
    return os.environ.get("AM_GH_API", "https://api.github.com").rstrip("/")


def web() -> str:
    return os.environ.get("AM_GH_WEB", "https://github.com").rstrip("/")


def raw() -> str:
    return os.environ.get("AM_GH_RAW", "https://raw.githubusercontent.com").rstrip("/")


def repo() -> str:
    return os.environ.get("AM_GH_REPO", REPO)


def wanted(rel: str, os_name: Optional[str]) -> bool:
    """True if the file (path relative to the project, with /) is part of an installation on `os_name`:
    not in a server-only folder and not the launcher of another operating system."""
    top = rel.split("/", 1)[0]
    if top in SKIP_DIRS or rel in SKIP_FILES:
        return False
    if os_name and rel.startswith(LAUNCHER_DIR + "/"):
        own = LAUNCHERS.get(os_name)
        return rel.rsplit("/", 1)[-1] == own
    return True
