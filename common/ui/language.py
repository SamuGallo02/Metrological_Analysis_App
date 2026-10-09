"""Language selection and download. Does not depend on any page."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QProgressBar, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QAbstractItemView)

from ..i18n import LanguageManager, current_language, tr, tr_error
from ..params import DEFAULT_LANGUAGE, LANGUAGES
from .qt_utils import run_async


class LanguageWidget(QWidget):
    """List of languages: English is always installed, the others are downloaded from the website."""

    def __init__(self, manager: Optional[LanguageManager] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.mgr = manager or LanguageManager()
        self.available: Dict[str, Dict[str, Any]] = {}
        lay = QVBoxLayout(self)
        self.info = QLabel(tr("English is always installed. Other languages are downloaded once and then work offline. "
                              "The change is applied the next time you start the application."))
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("Language"), tr("Status"), ""])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.btn_main = QPushButton()
        self.btn_main.clicked.connect(self._main_action)
        self.btn_remove = QPushButton(tr("Remove"))
        self.btn_remove.clicked.connect(self._remove)
        self.btn_refresh = QPushButton(tr("Check for languages"))
        self.btn_refresh.clicked.connect(self.fetch)
        row.addWidget(self.btn_main)
        row.addWidget(self.btn_remove)
        row.addStretch(1)
        row.addWidget(self.btn_refresh)
        lay.addLayout(row)
        self.bar = QProgressBar()
        self.bar.hide()
        lay.addWidget(self.bar)
        self.status = QLabel("")
        lay.addWidget(self.status)
        self.table.itemSelectionChanged.connect(self._buttons)
        self._fill()
        self.fetch()

    # ---- data --------------------------------------------------------------
    def fetch(self) -> None:
        self.status.setText(tr("Checking the available languages..."))

        def done(entries: List[Dict[str, Any]]) -> None:
            self.available = {e["code"]: e for e in entries}
            self.status.setText("")
            self._fill()

        def fail(e: Exception) -> None:
            self.status.setText(tr("Could not reach the language server: only installed languages are shown."))
            self._fill()

        run_async(self, self.mgr.fetch_index, done, fail)

    def _state(self, code: str) -> str:
        if code not in self.mgr.installed():
            return "available" if code in self.available else "unavailable"
        entry = self.available.get(code)
        if entry and int(entry.get("version", 0)) > self.mgr.installed_version(code):
            return "update"
        return "installed"

    def _fill(self) -> None:
        sel = self._code()
        self.table.setRowCount(len(LANGUAGES))
        names = {"installed": tr("Installed"), "available": tr("Available to download"),
                 "update": tr("Update available"), "unavailable": tr("Not available")}
        for i, (code, (en, native)) in enumerate(LANGUAGES.items()):
            self.table.setItem(i, 0, QTableWidgetItem(f"{native}  ({en})"))
            st = names[self._state(code)] + (" · " + tr("in use") if code == current_language() else "")
            self.table.setItem(i, 1, QTableWidgetItem(st))
            self.table.item(i, 0).setData(Qt.ItemDataRole.UserRole, code)
            if code == sel:
                self.table.selectRow(i)
        self._buttons()

    def _code(self) -> Optional[str]:
        r = self.table.currentRow()
        it = self.table.item(r, 0) if r >= 0 else None
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _buttons(self) -> None:
        code = self._code()
        st = self._state(code) if code else "unavailable"
        self.btn_main.setEnabled(st != "unavailable" and not (st == "installed" and code == current_language()))
        self.btn_main.setText({"available": tr("Download and use"), "update": tr("Update"),
                               "installed": tr("Use this language")}.get(st, tr("Use this language")))
        self.btn_remove.setEnabled(bool(code) and code != DEFAULT_LANGUAGE and code in self.mgr.installed())

    # ---- actions -----------------------------------------------------------
    def _main_action(self) -> None:
        code = self._code()
        if not code:
            return
        if self._state(code) in ("available", "update"):
            self.bar.setValue(0)
            self.bar.show()
            self.btn_main.setEnabled(False)
            run_async(self, lambda: self.mgr.install(self.available[code], self._progress),
                      lambda _p: self._activate(code), self._download_failed)
        else:
            self._activate(code)

    def _progress(self, done: int, total: int) -> None:
        self.bar.setValue(int(100 * done / max(1, total)))

    def _download_failed(self, e: Exception) -> None:
        self.bar.hide()
        self._buttons()
        QMessageBox.warning(self, tr("Error"), tr_error(e))

    def _activate(self, code: str) -> None:
        self.bar.hide()
        self.mgr.activate(code)
        self._fill()
        QMessageBox.information(self, tr("Language"), tr("The language will change the next time you start the application."))

    def _remove(self) -> None:
        code = self._code()
        if code and QMessageBox.question(self, tr("Remove"), tr("Remove the language pack?")) == QMessageBox.StandardButton.Yes:
            self.mgr.remove(code)
            self._fill()


class LanguageDialog(QDialog):
    """Window with the language list: opened by the language button."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Language"))
        self.setMinimumSize(520, 420)
        lay = QVBoxLayout(self)
        self.widget = LanguageWidget(parent=self)
        lay.addWidget(self.widget, 1)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)


class LanguageButton(QPushButton):
    """Button showing the language in use (in its own language); it opens the language window."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        code = current_language()
        native = LANGUAGES.get(code, LANGUAGES[DEFAULT_LANGUAGE])[1]
        self.setText(f"\U0001F310  {native}")
        self.setToolTip(tr("Change language"))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(lambda: LanguageDialog(self.window()).exec())
