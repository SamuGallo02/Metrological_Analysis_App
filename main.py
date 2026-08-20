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

    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("StereoMetrologyAnalysis")

    window = MainWindow()
    window.showMaximized()  # Apertura forzata a schermo intero

    sys.exit(app.exec())


if __name__ == "__main__":
    bootstrap()