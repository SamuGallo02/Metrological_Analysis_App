"""
Widgets and dialogs shared across the application's pages:
clickable image label,
standard top bar, image rendering/zoom.

Autore: Samuele Gallo
"""

from __future__ import annotations

from typing import Optional

import cv2
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from common.i18n import tr


class ClickableImageLabel(QLabel):
    """QLabel that emits a signal on click (used to open the enlarged preview)."""
    clicked = Signal()

    def mousePressEvent(self, event) -> None:
        self.clicked.emit()
        super().mousePressEvent(event)


_manual_opener = None


def set_manual_opener(opener) -> None:
    """Registers the function `opener(parent)` that opens the manual (set by the app: common does not know the pages)."""
    global _manual_opener
    _manual_opener = opener


def build_top_bar(parent: QWidget, on_home) -> QHBoxLayout:
    """
    Standard top bar of every page: "back to home" button on the
    left, "Manuale d'uso" (user manual) button on the right. Returns the
    ready-made layout to add at the top of the calling page's layout.
    """
    bar = QHBoxLayout()

    btn_back = QPushButton(tr("← Back to home"))
    btn_back.clicked.connect(on_home)
    bar.addWidget(btn_back)

    bar.addStretch(1)

    btn_manual = QPushButton(tr("User manual"))
    btn_manual.clicked.connect(lambda: _manual_opener(parent) if _manual_opener else None)
    btn_manual.setVisible(_manual_opener is not None)
    bar.addWidget(btn_manual)

    return bar


def render_image_to_label(label: QLabel, image) -> None:
    """Scales and shows an OpenCV image (BGR) inside a QLabel, fitting it to its current size."""
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
    """Opens a window with the enlarged image at full resolution (up to 90% of the screen)."""
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
