"""Schermata di scelta dell'analisi: in alto la demo (se fornita), sotto le 4 analisi. Niente pulsanti
Foto/Video separati nella home: si arriva qui con il pulsante "Analisi"."""
from __future__ import annotations

from typing import Callable, Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from common.i18n import tr, tr_dyn

from .params import ANALYSES, CARD_MIN_SIZE, MAX_WIDTH


class AnalysisCard(QFrame):
    clicked = Signal()

    def __init__(self, title: str, description: str, color: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(*CARD_MIN_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"QFrame {{ background-color: {color}; border-radius: 10px; }}"
                           f"QFrame:hover {{ background-color: {color}dd; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(15, 15, 15, 15)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t = QLabel(title)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet("font-size: 15px; font-weight: bold; color: white; background: transparent;")
        d = QLabel(description)
        d.setAlignment(Qt.AlignmentFlag.AlignCenter)
        d.setWordWrap(True)
        d.setStyleSheet("font-size: 12px; color: #f0f0f0; background: transparent;")
        lay.addWidget(t)
        lay.addWidget(d)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class AnalysisHub(QWidget):
    """`requested(id)` quando l'utente sceglie un'analisi; l'applicazione apre la pagina corrispondente.
    `demo`: widget della demo (es. il pulsante Demo Webcam); compare solo in questa schermata.
    `on_home`: callback del pulsante "Torna alla home"."""

    requested = Signal(str)

    def __init__(self, on_home: Optional[Callable[[], None]] = None, demo: Optional[QWidget] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.cards: Dict[str, AnalysisCard] = {}
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        if on_home:
            back = QPushButton(tr("← Back to home"))
            back.clicked.connect(on_home)
            top.addWidget(back)
        top.addStretch(1)
        self.demo = demo
        if demo is not None:
            top.addWidget(demo)                       # la demo vive solo qui, in alto
        lay.addLayout(top)
        lay.addStretch(1)

        title = QLabel(tr("Choose the type of analysis"))
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        lay.addSpacing(24)

        grid = QGridLayout()
        grid.setSpacing(20)
        for i, (aid, name, desc, color) in enumerate(ANALYSES):
            card = AnalysisCard(tr_dyn(name), tr_dyn(desc), color)
            card.clicked.connect(lambda a=aid: self.requested.emit(a))
            grid.addWidget(card, i // 2, i % 2)
            self.cards[aid] = card
        holder = QWidget()
        holder.setMaximumWidth(MAX_WIDTH)
        holder.setLayout(grid)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(holder, 10)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(2)
