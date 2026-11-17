"""The "Folders" page: first the choice between what is on this computer, what is on the server and the groups,
then the chosen section with a way back to the choice."""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from common.i18n import tr
from common.ui.layout import centered_content
from common.ui.widgets import GROUP_COLOR, LOCAL_COLOR, MenuCard, SERVER_COLOR

from corpse.functions.users.session import Session
from .browser import ServerFoldersWidget
from .folders_local import LocalFoldersWidget
from .groups_page import GroupsPage

CHOICE, SECTION = 0, 1


class FoldersPage(QWidget):
    """Local / Server / Groups."""

    def __init__(self, session: Session, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        self.sections = {}
        lay = QVBoxLayout(self)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        choice = QWidget()
        cl = QVBoxLayout(choice)
        cl.addStretch(1)
        title = QLabel(f"<h2>{tr('Folders')}</h2>")
        subtitle = QLabel(tr("Choose where you want to work"))
        for w in (title, subtitle):
            w.setStyleSheet("qproperty-alignment: AlignCenter;")
            cl.addWidget(w)
        grid = QGridLayout()
        grid.setSpacing(20)
        cards = [
            (tr("Local"), tr("The folders of this computer: look at them, tidy them up and send them to the server."),
             LOCAL_COLOR, lambda: self.open_section("local")),
            (tr("Server"), tr("Photos, videos, datasets and models of the server, and your own folder."),
             SERVER_COLOR, lambda: self.open_section("server")),
            (tr("Work groups"), tr("The shared folders of your groups, their members and what is waiting."),
             GROUP_COLOR, lambda: self.open_section("groups")),
        ]
        for i, (label, description, color, cb) in enumerate(cards):
            grid.addWidget(MenuCard(label, description, color, onClick=cb), 0, i)
        cl.addLayout(centered_content(grid, max_width=1000))
        cl.addStretch(2)
        self.stack.addWidget(choice)

        holder = QWidget()
        hl = QVBoxLayout(holder)
        bar = QHBoxLayout()
        self.back = QPushButton(tr("← Folders"))
        self.back.clicked.connect(self.show_choice)
        bar.addWidget(self.back)
        bar.addStretch(1)
        hl.addLayout(bar)
        self.body = QStackedWidget()
        hl.addWidget(self.body, 1)
        self.stack.addWidget(holder)

    # ---- navigation -----------------------------------------------------
    def show_choice(self) -> None:
        self.stack.setCurrentIndex(CHOICE)

    def open_section(self, name: str) -> QWidget:
        """Builds the section the first time it is asked for, then only shows it again."""
        widget = self.sections.get(name)
        if widget is None:
            widget = {"local": lambda: LocalFoldersWidget(self.session),
                      "server": lambda: ServerFoldersWidget(self.session),
                      "groups": lambda: GroupsPage(self.session)}[name]()
            self.sections[name] = widget
            self.body.addWidget(widget)
        else:
            refresh: Optional[Callable] = getattr(widget, "refresh", None)
            if callable(refresh):
                refresh()
        self.body.setCurrentWidget(widget)
        self.stack.setCurrentIndex(SECTION)
        return widget
