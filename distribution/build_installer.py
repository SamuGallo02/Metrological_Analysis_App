#!/usr/bin/env python3
"""
Genera il file unico da distribuire (Installa.cmd + copia Installa.command per macOS)
unendo wrapper.in (Windows/sh) e installer_gui.py (la finestra di installazione).

Uso:  python distribution/build_installer.py          (scrive nella cartella del progetto)
      python distribution/build_installer.py DEST     (scrive in DEST)
"""
import os
import stat
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent

wrapper = (HERE / "wrapper.in").read_text(encoding="utf-8").replace("\r\n", "\n")
gui = (HERE / "installer_gui.py").read_text(encoding="utf-8").replace("\r\n", "\n")

for marker in ("::CMDLITERAL", "#PS_BEGIN", "##PYSRC_BEGIN"):
    assert marker not in gui, f"installer_gui.py contiene il marcatore riservato {marker}"
assert wrapper.rstrip().endswith("##PYSRC_BEGIN")

data = wrapper.rstrip("\n") + "\n" + gui
for name in ("Installa.cmd", "Installa.command"):
    f = OUT / name
    f.write_bytes(data.encode("utf-8"))   # LF: indispensabile per la parte sh
    f.chmod(f.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print("scritto", f)
