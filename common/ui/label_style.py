"""How the labels look, everywhere they are seen: in the previews, in the viewers and in the editor.

Two things are remembered in the settings of this computer (settings.json), because they are a matter of
eyesight, not of data:

  labels_visible   whether the shapes are drawn over the media (the "Labels" button of the views)
  label_color      "" to give each class its own colour, or one colour for all of them

A single colour is what a person needs when the picture fights the default one: red lines on a red fish are
unreadable, and in a second the user can switch them to yellow - for the time of a correction, or for good.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QColorDialog, QMenu, QToolButton, QWidget

from common.i18n import tr
from common.paths import user_data_dir
from common.settings import Settings

KEY_VISIBLE = "labels_visible"
KEY_COLOR = "label_color"
_settings: Optional[Settings] = None
_override: Optional[QColor] = None          # kept in memory too, so every view agrees at once
_loaded = False


def _store() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings(user_data_dir())
    return _settings


def _load() -> None:
    global _loaded, _override
    if _loaded:
        return
    _loaded = True
    try:
        value = str(_store().get(KEY_COLOR, "") or "")
    except OSError:
        value = ""
    color = QColor(value) if value else QColor()
    _override = color if color.isValid() else None


# ---- are they shown? ---------------------------------------------------------
def labels_visible() -> bool:
    """The setting the views follow: draw the labels over the media, or show the media alone."""
    try:
        return bool(_store().get(KEY_VISIBLE, True))
    except OSError:
        return True


def set_labels_visible(visible: bool) -> None:
    try:
        _store().update(**{KEY_VISIBLE: bool(visible)})
    except OSError:
        pass


# ---- what colour are they? ----------------------------------------------------
def class_color(cls: int) -> QColor:
    """The colour of a class when each one has its own: distinct and always the same for that class."""
    return QColor.fromHsv((int(cls) * 67) % 360, 220, 255)


def color_override() -> Optional[QColor]:
    _load()
    return QColor(_override) if _override is not None else None


def set_color_override(color: Optional[QColor], remember: bool = True) -> None:
    """One colour for every label, or None to go back to one colour per class. `remember=False` keeps it only
    for this session - the "just while I draw" case."""
    global _override, _loaded
    _loaded = True
    _override = QColor(color) if color is not None and QColor(color).isValid() else None
    if not remember:
        return
    try:
        _store().update(**{KEY_COLOR: _override.name() if _override else ""})
    except OSError:
        pass


def color_for(cls: int) -> QColor:
    """The colour to draw a shape of this class with, chosen colour first."""
    chosen = color_override()
    return chosen if chosen is not None else class_color(cls)


def color_icon(color: QColor, size: int = 16) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(color)
    return QIcon(pix)


class LabelColorButton(QToolButton):
    """Button of the views: changes the colour of the labels for contrast, now and everywhere."""

    changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setToolTip(tr("Colour of the labels: change it when they are hard to see."))
        menu = QMenu(self)
        self.act_pick = menu.addAction(tr("Choose a colour..."))
        self.act_pick.triggered.connect(self._pick)
        self.act_classes = menu.addAction(tr("One colour per class"))
        self.act_classes.triggered.connect(lambda: self._apply(None))
        menu.addSeparator()
        for name, color in ((tr("Yellow"), "#ffe100"), (tr("Green"), "#00e676"), (tr("Magenta"), "#ff00d0"),
                            (tr("White"), "#ffffff"), (tr("Black"), "#000000")):
            act = menu.addAction(color_icon(QColor(color)), name)
            act.triggered.connect(lambda _checked=False, c=color: self._apply(QColor(c)))
        self.setMenu(menu)
        self._refresh()

    def _pick(self) -> None:
        start = color_override() or class_color(0)
        chosen = QColorDialog.getColor(start, self, tr("Colour of the labels"))
        if chosen.isValid():
            self._apply(chosen)

    def _apply(self, color: Optional[QColor]) -> None:
        set_color_override(color)
        self._refresh()
        self.changed.emit()

    def _refresh(self) -> None:
        chosen = color_override()
        self.setText(tr("Colour"))
        self.setIcon(color_icon(chosen if chosen is not None else class_color(0)))
