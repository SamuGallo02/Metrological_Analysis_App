#!/usr/bin/env python3
"""
Generates the single file to distribute (Installa.cmd + a copy Installa.command for macOS)
by merging wrapper.in (Windows/sh) and installer_gui.py (the installation window).

Usage:  python common/ambient/distribution/build_installer.py   (writes to common/ambient/distribution/output/)
        python common/ambient/distribution/build_installer.py DEST     (writes to DEST)
"""
import os
import stat
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "output"

wrapper = (HERE / "wrapper.in").read_text(encoding="utf-8").replace("\r\n", "\n")
gui = (HERE / "installer_gui.py").read_text(encoding="utf-8").replace("\r\n", "\n")

for marker in ("::CMDLITERAL", "#PS_BEGIN", "##PYSRC_BEGIN"):
    assert marker not in gui, f"installer_gui.py contiene il marcatore riservato {marker}"
assert wrapper.rstrip().endswith("##PYSRC_BEGIN")

data = wrapper.rstrip("\n") + "\n" + gui
for name in ("Installa.cmd", "Installa.command"):
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / name
    f.write_bytes(data.encode("utf-8"))   # LF: essential for the sh part
    f.chmod(f.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print("scritto", f)
