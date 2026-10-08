"""
Stato dell'installazione (.install_state.json nella cartella del progetto).

E' l'UNICO controllo fatto all'avvio dell'app (e dai launcher): il file esiste
=> installazione completata. Niente verifiche pacchetto per pacchetto.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = PROJECT_ROOT / ".install_state.json"
SCHEMA = 1

VENV_DIRS = {"windows": "venv", "macos": "venv_mac", "linux": "venv_linux"}


def venv_dir(os_name: str) -> Path:
    return PROJECT_ROOT / VENV_DIRS[os_name]


def venv_python(os_name: str) -> Path:
    base = venv_dir(os_name)
    return base / ("Scripts/python.exe" if os_name == "windows" else "bin/python")


def venv_gui_python(os_name: str) -> Path:
    """Interprete per avviare la GUI (su Windows senza console)."""
    if os_name == "windows":
        return venv_dir(os_name) / "Scripts" / "pythonw.exe"
    return venv_python(os_name)


def load() -> Dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(data: Dict[str, Any]) -> None:
    data["schema"] = SCHEMA
    STATE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def mark_component(component: str, **info: Any) -> None:
    data = load()
    info["installed"] = True
    info["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    data[component] = info
    save(data)


def is_installed(component: str = "core") -> bool:
    return bool(load().get(component, {}).get("installed"))
