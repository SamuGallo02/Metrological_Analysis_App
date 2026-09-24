"""
Pagine di selezione della modalita' (Singola/Singolo o Stereo), mostrate
dopo aver scelto "Analisi Foto" o "Analisi Video" dalla home.

Autore: Samuele Gallo
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from gui.common_widgets import build_top_bar
from gui.home_layout import centered_content


class _ModeSelectorPage(QWidget):
    """Scheletro comune: due pulsanti (Singola/Singolo, Stereo) + torna alla home."""

    def __init__(
            self, on_home: Callable[[], None], title: str,
            single_label: str, single_desc: str, on_single: Callable[[], None],
            stereo_label: str, stereo_desc: str, on_stereo: Callable[[], None],
            parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        root_layout = QVBoxLayout(self)
        root_layout.addLayout(build_top_bar(self, on_home))
        root_layout.addStretch(1)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 22px; font-weight: bold;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root_layout.addWidget(lbl_title)

        grid = QGridLayout()
        grid.setSpacing(20)

        self.btn_single = None
        self.btn_stereo = None

        for col, (label, desc, color, callback) in enumerate([
            (single_label, single_desc, "#1565c0", on_single),
            (stereo_label, stereo_desc, "#2e7d32", on_stereo),
        ]):
            btn = QPushButton(f"{label}\n\n{desc}")
            btn.setMinimumSize(280, 130)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color}; color: white; font-weight: bold;
                    font-size: 14px; border-radius: 8px; padding: 10px;
                }}
            """)
            btn.clicked.connect(callback)
            grid.addWidget(btn, 0, col)
            if col == 0:
                self.btn_single = btn
            else:
                self.btn_stereo = btn

        root_layout.addLayout(centered_content(grid))
        root_layout.addStretch(2)


class FotoModeSelectorPage(_ModeSelectorPage):
    """Scelta tra Foto Singola e Foto Stereo."""

    def __init__(self, on_home, on_singola, on_stereo, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            on_home, "Analisi Foto — scegli la modalità",
            "Singola", "Una foto alla volta: solo rilevamento,\nnessuna misura.", on_singola,
            "Stereo", "Coppia di foto rx/lx: misure reali\ndi dimensioni e distanza.", on_stereo,
            parent=parent,
        )


class VideoModeSelectorPage(_ModeSelectorPage):
    """Scelta tra Video Singolo e Video Stereo."""

    def __init__(self, on_home, on_singolo, on_stereo, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            on_home, "Analisi Video — scegli la modalità",
            "Singolo", "Un solo video: rilevamento e\ntracciamento, nessuna misura.", on_singolo,
            "Stereo", "Due video sincronizzati rx/lx:\nmisure reali frame per frame.", on_stereo,
            parent=parent,
        )
