"""
Widget e finestre di dialogo condivisi tra le pagine dell'applicativo:
etichetta immagine cliccabile, finestra del manuale (work in progress),
barra superiore standard, rendering/zoom delle immagini.

Autore: Samuele Gallo
"""

from __future__ import annotations

from typing import Optional

import cv2
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget


class ClickableImageLabel(QLabel):
    """QLabel che emette un segnale al click (usata per aprire l'anteprima ingrandita)."""
    clicked = Signal()

    def mousePressEvent(self, event) -> None:
        self.clicked.emit()
        super().mousePressEvent(event)


class ManualDialog(QDialog):
    """
    Finestra del manuale d'uso — contenuto ancora da scrivere (work in
    progress). Il testo qui sotto e' un semplice segnaposto: quando avrai
    pronto il manuale vero, sostituisci il testo passato a setPlainText().
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manuale d'uso")
        self.resize(520, 420)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h3>Manuale d'uso — Work in Progress</h3>"))

        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(
            "Questa finestra conterra' il manuale d'uso completo dell'applicativo.\n\n"
            "Contenuto non ancora disponibile — in arrivo in una prossima versione."
        )
        layout.addWidget(text)

        btn_close = QPushButton("Chiudi")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


def build_top_bar(parent: QWidget, on_home) -> QHBoxLayout:
    """
    Barra superiore standard di ogni pagina: pulsante "torna alla home" a
    sinistra, pulsante "Manuale d'uso (WIP)" a destra. Ritorna il layout
    gia' pronto da aggiungere in cima al layout della pagina chiamante.
    """
    bar = QHBoxLayout()

    btn_back = QPushButton("← Torna alla home")
    btn_back.clicked.connect(on_home)
    bar.addWidget(btn_back)

    bar.addStretch(1)

    btn_manual = QPushButton("Manuale d'uso (WIP)")
    btn_manual.clicked.connect(lambda: ManualDialog(parent).exec())
    bar.addWidget(btn_manual)

    return bar


def render_image_to_label(label: QLabel, image) -> None:
    """Scala e mostra un'immagine OpenCV (BGR) dentro una QLabel, adattandola alle sue dimensioni attuali."""
    if image is None:
        label.setText("Immagine non disponibile")
        label.setPixmap(QPixmap())
        return

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)

    target_w = max(label.width(), 100)
    target_h = max(label.height(), 100)
    pixmap = QPixmap.fromImage(qimg).scaled(
        target_w, target_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
    )
    label.setPixmap(pixmap)


def open_zoom_dialog(parent: QWidget, image) -> None:
    """Apre una finestra con l'immagine ingrandita a piena risoluzione (fino al 90% dello schermo)."""
    if image is None:
        return

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)

    screen = parent.screen()
    screen_geo = screen.availableGeometry() if screen else None
    max_w = int(screen_geo.width() * 0.9) if screen_geo else 1600
    max_h = int(screen_geo.height() * 0.9) if screen_geo else 1000

    scale_factor = min(1.0, max_w / w, max_h / h)
    target_w = max(1, int(w * scale_factor))
    target_h = max(1, int(h * scale_factor))

    pixmap = QPixmap.fromImage(qimg).scaled(
        target_w, target_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
    )

    dialog = QDialog(parent)
    dialog.setWindowTitle("Anteprima ingrandita")
    dialog_layout = QVBoxLayout(dialog)
    dialog_layout.setContentsMargins(4, 4, 4, 4)

    zoom_label = QLabel()
    zoom_label.setPixmap(pixmap)
    zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    dialog_layout.addWidget(zoom_label)

    dialog.resize(pixmap.width() + 16, pixmap.height() + 32)
    dialog.exec()
