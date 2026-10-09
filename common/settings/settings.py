"""User settings (settings.json) and atomic read/write of local JSON files."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from ..paths import user_data_dir


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data: Any) -> None:
    """Writes atomically and, where possible, readable only by the user."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Settings:
    """settings.json: server address, last user, language, local folders..."""

    def __init__(self, folder: Optional[Path] = None):
        self.dir = Path(folder) if folder else user_data_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.file = self.dir / "settings.json"

    def all(self) -> Dict[str, Any]:
        return read_json(self.file, {})

    def get(self, key: str, default: Any = None) -> Any:
        return self.all().get(key, default)

    def update(self, **kw: Any) -> None:
        data = self.all()
        data.update(kw)
        write_json(self.file, data)
