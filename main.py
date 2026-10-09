"""
Application for Stereo-Photogrammetric Metrological Analysis
============================================================
Main module for initializing the graphical interface
and orchestrating the system dependencies.

Autore: Samuele Gallo
"""

from __future__ import annotations

import ctypes
import os
import sys

# Registering the unique ID on Windows for the taskbar
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("StereoMetrology.AnalysisApp.1.0")
except Exception:
    pass

# Preemptively disabling the dynamic introspection hooks
os.environ["SHIBOKEN_DISABLE_IMPORTHOOK"] = "1"


def self_repair(deep: bool = False) -> None:
    """Checks the files of the virtual environment and, if some are damaged, repairs them (with a progress window)."""
    from pathlib import Path

    from common.ambient.repair_dialog import repair_at_startup

    if repair_at_startup(Path(__file__).resolve().parent, deep) == "quit":
        sys.exit(0)  # the repair continues in the background and reopens the app


def bootstrap() -> None:
    """Preloads the scientific libraries and initializes the Qt application."""
    if "--no-check" not in sys.argv:
        self_repair()  # before importing the libraries: a truncated DLL would crash the import
    try:
        import cv2
        import numpy as np
        import pandas as pd

        from corpse.functions.analysis.analysis import ObjectAnalyzer
        from corpse.functions.analysis.reporting import compute_summary, export_csv
    except (ImportError, OSError) as err:
        print(f"[ERROR] Cannot load the core modules: {err}")
        if "--no-check" not in sys.argv:
            self_repair(deep=True)  # sizes were fine: look at the content of every file
        sys.exit(1)

    from pathlib import Path

    from PySide6.QtWidgets import QApplication, QDialog

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("StereoMetrologyAnalysis")

    from common.i18n import init_language
    from common.paths import MODELS_DIR, RESULTS_DIR, STEREO_PHOTO_DIR, TRAINING_DIR
    from corpse.gui.home.home_gui import AppWindow
    from corpse.functions.users.session import Session
    from corpse.functions.users.store import LocalStore
    from corpse.gui.users import LoginDialog

    init_language()  # language chosen by the user (English if none)

    root = Path(__file__).resolve().parent
    session = Session(LocalStore(default_folders={
        "photos": STEREO_PHOTO_DIR, "models": MODELS_DIR, "datasets": TRAINING_DIR, "results": RESULTS_DIR,
    }))
    if not session.resume():  # valid saved session, or server off with a previous session
        dialog = LoginDialog(session)  # login, registration, admin key or "continue without logging in"
        dialog.showMaximized()  # opens full screen; the user can restore and maximize it again
        if dialog.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)

    window = AppWindow(session)
    window.showMaximized()  # Forced full-screen opening

    sys.exit(app.exec())


if __name__ == "__main__":
    bootstrap()