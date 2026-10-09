"""Builds the downloadable language packs from common/translations/<code>.py.

    python -m tools.build_language_packs --check            # check only (coverage, placeholders, manual)
    python -m tools.build_language_packs --out site/locales # creates <code>.json and index.json to publish on the site

Each file common/translations/<code>.py contains:  VERSION = 1,  STRINGS = {"English text": "translation"},  MANUAL = "..."
Increase VERSION when you change a translation: the app offers the update.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from common.params import DEFAULT_LANGUAGE, LANGUAGES            # noqa: E402
from corpse.gui.manual.content import MANUAL                                  # noqa: E402
from tools.extract_strings import extract                          # noqa: E402

_PH = re.compile(r"\{[a-z_]+\}")
_TAG = re.compile(r"</?[a-z]+>")
_H2 = re.compile(r"(?m)^## ")
_H1 = re.compile(r"(?m)^# ")


def problems_for(code: str, strings: Dict[str, str], manual: str, keys: set) -> List[str]:
    out: List[str] = []
    for k in sorted(keys - set(strings)):
        out.append(f"missing: {k!r}")
    for k in sorted(set(strings) - keys):
        out.append(f"unused: {k!r}")
    for k, v in strings.items():
        if k not in keys:
            continue
        if not isinstance(v, str) or not v.strip():
            out.append(f"empty: {k!r}")
            continue
        if sorted(_PH.findall(k)) != sorted(_PH.findall(v)):
            out.append(f"placeholders differ: {k!r} -> {v!r}")
        if sorted(_TAG.findall(k)) != sorted(_TAG.findall(v)):
            out.append(f"html tags differ: {k!r} -> {v!r}")
    if not manual.strip():
        out.append("manual missing")
    else:
        if len(_H2.findall(manual)) != len(_H2.findall(MANUAL)) or len(_H1.findall(manual)) != 1:
            out.append("manual: number of headings differs from the English manual")
        if manual.count("**") != MANUAL.count("**"):
            out.append("manual: number of ** (bold) markers differs")
        if len(re.findall(r"(?m)^(\d+\.|-) ", manual)) != len(re.findall(r"(?m)^(\d+\.|-) ", MANUAL)):
            out.append("manual: number of list items differs")
    return out


def load(code: str):
    return importlib.import_module(f"common.translations.{code}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="folder for <code>.json and index.json")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--only", nargs="*", help="language codes to process")
    a = ap.parse_args(argv)
    keys, bad = extract()
    if bad:
        print("\n".join(bad))
        return 1
    index, failed = [], False
    for code, (en, native) in LANGUAGES.items():
        if code == DEFAULT_LANGUAGE or (a.only and code not in a.only):
            continue
        try:
            mod = load(code)
        except ModuleNotFoundError:
            print(f"[{code}] no translation file")
            failed = True
            continue
        probs = problems_for(code, mod.STRINGS, mod.MANUAL, keys)
        print(f"[{code}] {len(keys) - sum(p.startswith('missing') for p in probs)}/{len(keys)} strings, "
              f"{len(probs)} problems")
        for p in probs[:25]:
            print("   ", p)
        failed |= bool(probs)
        if a.out and not probs:
            out = Path(a.out)
            out.mkdir(parents=True, exist_ok=True)
            data = json.dumps({"code": code, "name": en, "native": native, "version": mod.VERSION,
                               "strings": {k: mod.STRINGS[k] for k in sorted(keys)}, "manual": mod.MANUAL},
                              ensure_ascii=False, indent=1).encode("utf-8")
            (out / f"{code}.json").write_bytes(data)
            index.append({"code": code, "name": en, "native": native, "version": mod.VERSION, "file": f"{code}.json",
                          "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
    if a.out and index and not failed:
        (Path(a.out) / "index.json").write_text(json.dumps({"languages": index}, ensure_ascii=False, indent=1),
                                                encoding="utf-8")
        print(f"written {len(index)} packs + index.json in {a.out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
