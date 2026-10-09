"""Translations. The base language is English (preinstalled): the texts in the code ARE the keys.

    from common.i18n import tr
    label = tr("Sign in")                       # English text -> text in the chosen language
    msg = tr("{n} files uploaded.", n=3)         # named placeholder

The other languages are downloadable JSON packs (LanguageManager) saved in the user's folder:
    {"code": "it", "name": "Italian", "native": "Italiano", "version": 1,
     "strings": {"Sign in": "Accedi", ...}, "manual": "# ..."}
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urljoin

from .params import DEFAULT_LANGUAGE, LANG_INDEX_URL, LANGUAGES, NET_TIMEOUT
from .paths import user_data_dir
from .settings import Settings, read_json

_lang: str = DEFAULT_LANGUAGE
_strings: Dict[str, str] = {}
_manual: str = ""


def tr(text: str, **kw: Any) -> str:
    """Translates a literal text (the pack coverage check looks for it in the code)."""
    return tr_dyn(text, **kw)


def tr_dyn(text: str, **kw: Any) -> str:
    """Like tr() but for non-literal texts (e.g. messages received from the server): it is not extracted from the code."""
    out = _strings.get(text, text)
    if kw:
        try:
            return out.format(**kw)
        except (KeyError, IndexError, ValueError):
            return text.format(**kw)
    return out


def N_(text: str) -> str:
    """Marks a text to translate that is shown later with tr_dyn() (e.g. lists in the parameter files)."""
    return text


def tr_error(e: BaseException) -> str:
    """Message of an error in the current language (AppErrors carry key and parameters)."""
    key, params = getattr(e, "key", None), getattr(e, "params", None)
    return tr_dyn(key, **(params or {})) if key else str(e)


def current_language() -> str:
    return _lang


def current_manual() -> str:
    """Manual text in the current language ('' if the pack does not contain it)."""
    return _manual


def set_language(code: str, folder: Optional[Path] = None) -> bool:
    """Activates an already installed language. 'en' is always available. Returns False if not installed."""
    global _lang, _strings, _manual
    if code == DEFAULT_LANGUAGE:
        _lang, _strings, _manual = DEFAULT_LANGUAGE, {}, ""
        return True
    pack = read_json(_packs_dir(folder) / f"{code}.json", None)
    if not pack or pack.get("code") != code or not isinstance(pack.get("strings"), dict):
        return False
    _lang, _strings, _manual = code, pack["strings"], pack.get("manual", "")
    return True


def init_language(folder: Optional[Path] = None) -> str:
    """To be called at startup: applies the language saved in the settings (if still installed)."""
    code = Settings(folder).get("language", DEFAULT_LANGUAGE)
    if not set_language(code, folder):
        set_language(DEFAULT_LANGUAGE)
    return _lang


def _packs_dir(folder: Optional[Path] = None) -> Path:
    return (Path(folder) if folder else user_data_dir()) / "languages"


class LanguageManager:
    """Listing, download, removal and activation of language packs."""

    def __init__(self, folder: Optional[Path] = None, index_url: Optional[str] = None):
        self.folder = Path(folder) if folder else user_data_dir()
        self.index_url = index_url or LANG_INDEX_URL
        self.dir = _packs_dir(self.folder)

    def installed(self) -> List[str]:
        codes = [DEFAULT_LANGUAGE]
        if self.dir.is_dir():
            codes += sorted(p.stem for p in self.dir.glob("*.json") if p.stem in LANGUAGES and p.stem != DEFAULT_LANGUAGE)
        return codes

    def installed_version(self, code: str) -> int:
        if code == DEFAULT_LANGUAGE:
            return 0
        return int((read_json(self.dir / f"{code}.json", {}) or {}).get("version", 0))

    def fetch_index(self) -> List[Dict[str, Any]]:
        """[{code, name, native, version, file, sha256, size}] of the downloadable packs."""
        with urllib.request.urlopen(self.index_url, timeout=NET_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [e for e in data.get("languages", []) if e.get("code") in LANGUAGES and e["code"] != DEFAULT_LANGUAGE]

    def install(self, entry: Dict[str, Any], progress: Optional[Callable[[int, int], None]] = None) -> Path:
        """Downloads and verifies (SHA-256) the pack described by an index entry."""
        url = urljoin(self.index_url, entry["file"])
        with urllib.request.urlopen(url, timeout=NET_TIMEOUT) as r:
            total = int(r.headers.get("Content-Length") or entry.get("size") or 0)
            buf = bytearray()
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                buf += chunk
                if progress:
                    progress(len(buf), total or len(buf))
        if entry.get("sha256") and hashlib.sha256(buf).hexdigest() != entry["sha256"].lower():
            raise ValueError("The downloaded language pack is corrupted. Try again.")
        pack = json.loads(bytes(buf).decode("utf-8"))
        if pack.get("code") != entry["code"] or not isinstance(pack.get("strings"), dict):
            raise ValueError("Invalid language pack.")
        self.dir.mkdir(parents=True, exist_ok=True)
        dest = self.dir / f"{entry['code']}.json"
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(bytes(buf))
        os.replace(tmp, dest)
        return dest

    def remove(self, code: str) -> None:
        if code == DEFAULT_LANGUAGE:
            return
        if _lang == code:
            set_language(DEFAULT_LANGUAGE)
            Settings(self.folder).update(language=DEFAULT_LANGUAGE)
        try:
            (self.dir / f"{code}.json").unlink()
        except OSError:
            pass

    def activate(self, code: str) -> bool:
        if not set_language(code, self.folder):
            return False
        Settings(self.folder).update(language=code)
        return True
