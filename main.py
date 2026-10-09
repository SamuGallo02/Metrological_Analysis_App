"""
Applicativo per l'Analisi Metrologica Stereo-Fotogrammetrica
============================================================
Modulo principale per l'inizializzazione dell'interfaccia grafica
e l'orchestrazione delle dipendenze di sistema.

Autore: Samuele Gallo
"""

from __future__ import annotations

import ctypes
import os
import sys

# Registrazione dell'ID univoco su Windows per la barra delle applicazioni
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("StereoMetrology.AnalysisApp.1.0")
except Exception:
    pass

# Disabilitazione preventiva degli hook di introspezione dinamica
os.environ["SHIBOKEN_DISABLE_IMPORTHOOK"] = "1"


def bootstrap() -> None:
    """Pre-carica le librerie scientifiche e inizializza l'applicazione Qt."""
    try:
        import cv2
        import numpy as np
        import pandas as pd

        from core.analysis import ObjectAnalyzer
        from core.reporting import compute_summary, export_csv
    except ImportError as err:
        print(f"[ERROR] Impossibile caricare i moduli fondamentali: {err}")
        sys.exit(1)

    from pathlib import Path

    from PySide6.QtWidgets import QApplication, QDialog

    app = QApplication(sys.argv)
    app.setApplicationName("StereoMetrologyAnalysis")

    from common.i18n import init_language
    from gui.home_gui import AppWindow
    from users.session import Session
    from users.store import LocalStore
    from users.ui import LoginDialog

    init_language()  # lingua scelta dall'utente (inglese se nessuna)

    root = Path(__file__).resolve().parent
    session = Session(LocalStore(default_folders={
        "photos": root / "Dataset_Foto_Stereo", "models": root / "models",
        "datasets": root / "Dataset_Training", "results": root / "Results",
    }))
    if not session.resume():  # sessione salvata valida, oppure server spento con sessione precedente
        dialog = LoginDialog(session)  # accesso, registrazione, chiave admin o "continua senza accedere"
        dialog.showMaximized()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)

    window = AppWindow(session)
    window.showMaximized()  # Apertura forzata a schermo intero

    sys.exit(app.exec())


if __name__ == "__main__":
    bootstrap()