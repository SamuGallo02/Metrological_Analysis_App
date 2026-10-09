"""Manual page: index on the left, text on the right, search. Uses the manual of the current language."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QListWidget, QTextBrowser, QVBoxLayout, QWidget

from common.i18n import current_manual, tr

from .content import MANUAL


def split_sections(markdown: str) -> List[Tuple[str, str]]:
    """[(title, text)]: the text before the first '##' is the overview (title = '# ...')."""
    parts = re.split(r"(?m)^## ", markdown.strip())
    head = parts[0].strip()
    title = re.match(r"#\s+(.*)", head)
    out = [(title.group(1) if title else "", head)]
    for p in parts[1:]:
        t, _, body = p.partition("\n")
        out.append((t.strip(), "## " + t.strip() + "\n" + body))
    return out


class ManualWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.sections = split_sections(current_manual() or MANUAL)
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search the manual..."))
        self.search.textChanged.connect(self._filter)
        self.index = QListWidget()
        self.index.setMaximumWidth(240)
        self.index.currentRowChanged.connect(self._show)
        left.addWidget(self.search)
        left.addWidget(self.index, 1)
        lay.addLayout(left)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        lay.addWidget(self.view, 1)
        self._filter("")

    def _filter(self, text: str) -> None:
        q = text.strip().lower()
        self.index.clear()
        self._shown = [i for i, (t, body) in enumerate(self.sections) if not q or q in (t + body).lower()]
        for i in self._shown:
            self.index.addItem(self.sections[i][0])
        if self._shown:
            self.index.setCurrentRow(0)
        else:
            self.view.setPlainText(tr("No result."))

    def _show(self, row: int) -> None:
        if 0 <= row < len(self._shown):
            self.view.setMarkdown(self.sections[self._shown[row]][1])
