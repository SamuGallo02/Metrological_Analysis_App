"""Traduzioni. La lingua base e' l'inglese (preinstallata): i testi nel codice SONO le chiavi.

    from common.i18n import tr
    label = tr("Sign in")                       # testo inglese -> testo nella lingua scelta
    msg = tr("{n} files uploaded.", n=3)         # segnaposto con nome

Gli altri idiomi sono pacchetti JSON scaricabili (LanguageManager) salvati nella cartella dell'utente:
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
    """Traduce un testo letterale (il controllo di copertura dei pacchetti lo cerca nel codice)."""
    return tr_dyn(text, **kw)


def tr_dyn(text: str, **kw: Any) -> str:
    """Come tr() ma per testi non letterali (es. messaggi ricevuti dal server): non e' estratto dal codice."""
    out = _strings.get(text, text)
    if kw:
        try:
            return out.format(**kw)
        except (KeyError, IndexError, ValueError):
            return text.format(**kw)
    return out


def N_(text: str) -> str:
    """Segna un testo da tradurre che viene mostrato piu' tardi con tr_dyn() (es. elenchi nei file di parametri)."""
    return text


def tr_error(e: BaseException) -> str:
    """Messaggio di un errore nella lingua corrente (gli AppError portano chiave e parametri)."""
    key, params = getattr(e, "key", None), getattr(e, "params", None)
    return tr_dyn(key, **(params or {})) if key else str(e)


def current_language() -> str:
    return _lang


def current_manual() -> str:
    """Testo del manuale nella lingua corrente ('' se il pacchetto non lo contiene)."""
    return _manual


def set_language(code: str, folder: Optional[Path] = None) -> bool:
    """Attiva una lingua gia' installata. 'en' e' sempre disponibile. Ritorna False se non installata."""
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
    """Da chiamare all'avvio: applica la lingua salvata nelle impostazioni (se ancora installata)."""
    code = Settings(folder).get("language", DEFAULT_LANGUAGE)
    if not set_language(code, folder):
        set_language(DEFAULT_LANGUAGE)
    return _lang


def _packs_dir(folder: Optional[Path] = None) -> Path:
    return (Path(folder) if folder else user_data_dir()) / "languages"


class LanguageManager:
    """Elenco, download, rimozione e attivazione dei pacchetti lingua."""

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
        """[{code, name, native, version, file, sha256, size}] dei pacchetti scaricabili."""
        with urllib.request.urlopen(self.index_url, timeout=NET_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [e for e in data.get("languages", []) if e.get("code") in LANGUAGES and e["code"] != DEFAULT_LANGUAGE]

    def install(self, entry: Dict[str, Any], progress: Optional[Callable[[int, int], None]] = None) -> Path:
        """Scarica e verifica (SHA-256) il pacchetto descritto da una voce dell'indice."""
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
