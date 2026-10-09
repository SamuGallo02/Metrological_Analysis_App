"""
Shared layout helper: horizontally centers a block of content
instead of letting it expand over the whole window width — used by
Home, the mode selectors and the Training page (Stereo Analysis,
with its dense data table, stays at full width instead).

Autore: Samuele Gallo
"""

from __future__ import annotations

from typing import Union

from PySide6.QtWidgets import QHBoxLayout, QLayout, QWidget


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