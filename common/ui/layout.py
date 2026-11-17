"""
Shared layout helper: horizontally centers a block of content
instead of letting it expand over the whole window width — used by
Home, the mode selectors and the Training page (Stereo Analysis,
with its dense data table, stays at full width instead).

Autore: Samuele Gallo
"""

from __future__ import annotations

from typing import Sequence, Union

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLayout, QScrollArea, QWidget


def centered_content(inner: Union[QLayout, QWidget], max_width: int = 900) -> QHBoxLayout:
    """
    Wraps a layout or widget in a horizontally centered container
    with a maximum width, so the content does not stretch to cover
    the whole window on wide screens. Returns the ready-made QHBoxLayout
    to add to the calling page's layout.
    """
    container = QWidget()
    container.setMaximumWidth(max_width)
    if isinstance(inner, QLayout):
        container.setLayout(inner)
    else:
        outer = QHBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(inner)
        container.setLayout(outer)

    wrapper = QHBoxLayout()
    wrapper.addStretch(1)
    wrapper.addWidget(container)
    wrapper.addStretch(1)
    return wrapper

def fit_to_screen(window: QWidget, width: int, height: int, margin: float = 0.92) -> None:
    """Opens a window at the wanted size, but never larger than the screen it is on (laptops, 1366x768 screens,
    a second small monitor). Also keeps the minimum size within the screen, so the window can always be resized
    down far enough to be used and moved."""
    screen = window.screen() or QApplication.primaryScreen()
    if screen is None:                                     # no screen (tests, offscreen): keep the wanted size
        window.resize(width, height)
        return
    free = screen.availableGeometry()
    max_w, max_h = int(free.width() * margin), int(free.height() * margin)
    hint = window.minimumSize()
    window.setMinimumSize(min(hint.width(), max_w), min(hint.height(), max_h))
    window.resize(min(width, max_w), min(height, max_h))


def scrollable(content: QWidget, horizontal: bool = False) -> QScrollArea:
    """`content` inside a scroll area: a page that no longer fits (small screen, large font, window made smaller)
    scrolls instead of cutting off its buttons. The content keeps following the width of the window."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(content)
    if not horizontal:
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    return area


class Responsive(QObject):
    """Hides some widgets while the window is narrower than `breakpoint` pixels (for example the presentation
    column beside the login card). Watches the widget it is given and acts at every resize."""

    def __init__(self, watched: QWidget, breakpoint: int, hide: Sequence[QWidget]):
        super().__init__(watched)
        self.breakpoint, self.hide = breakpoint, list(hide)
        watched.installEventFilter(self)
        self.apply(watched.width())

    def apply(self, width: int) -> None:
        wide = width >= self.breakpoint
        for w in self.hide:
            w.setVisible(wide)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Resize:
            self.apply(event.size().width())
        return False
