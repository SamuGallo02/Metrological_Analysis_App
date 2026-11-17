"""User manual window: in the chosen language, with index and search."""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QDialog, QPushButton, QVBoxLayout, QWidget

from common.i18n import tr
from common.ui.layout import fit_to_screen

from .page import ManualWidget


class ManualDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("User manual"))
        fit_to_screen(self, 900, 600)
        layout = QVBoxLayout(self)
        layout.addWidget(ManualWidget(self), 1)
        btn_close = QPushButton(tr("Close"))
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)
