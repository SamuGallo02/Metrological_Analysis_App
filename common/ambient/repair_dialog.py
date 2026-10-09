"""Question shown at startup when the virtual environment has damaged files (see installer/integrity.py)."""
from __future__ import annotations

import sys

from common.i18n import init_language, tr


def ask_repair(listing: str) -> bool:
    """Asks whether to repair the damaged packages. If even Qt cannot start, repairs without asking."""
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        QApplication.instance() or QApplication(sys.argv)
        init_language()
        box = QMessageBox(QMessageBox.Icon.Warning, tr("Damaged files"),
                          tr("Some installed libraries are damaged:") + "\n\n" + listing + "\n\n"
                          + tr("Repair them now? Only the damaged packages are downloaded again, "
                               "then the app reopens by itself."),
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes
    except Exception:
        print("[WARNING] Damaged libraries:\n" + listing + "\nRepairing...")
        return True
