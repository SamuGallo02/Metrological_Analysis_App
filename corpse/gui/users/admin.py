"""User management and the administrator's main panel (users, database, training; analysis in the background)."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QTabBar,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from common.format import fmt_time
from common.i18n import tr, tr_error
from common.params import ROLE_SERVER, ROLE_USER
from common.ui.qt_utils import run_async

from corpse.functions.users.session import Session
from .browser import ServerBrowserWidget
from .labels import role_label


class NewUserDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(tr("New user"))
        form = QFormLayout(self)
        self.name = QLineEdit()
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.role = QTabBar()
        self.role.addTab(role_label(ROLE_USER))
        self.role.addTab(role_label(ROLE_SERVER))
        form.addRow(tr("Username:"), self.name)
        form.addRow(tr("Password:"), self.pw)
        form.addRow(tr("Type:"), self.role)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self) -> Tuple[str, str, str]:
        return self.name.text().strip(), self.pw.text(), (ROLE_USER, ROLE_SERVER)[self.role.currentIndex()]


def _table(headers: List[str], selectable: bool = True) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    if selectable:
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return t


class UserAdminWidget(QWidget):
    def __init__(self, session: Session, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        self.users: List[Dict[str, Any]] = []
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<h3>{tr('Users')}</h3>"))
        self.table = _table([tr("User"), tr("Name"), tr("Type"), tr("Status"), tr("Created"), tr("Last sign-in")])
        lay.addWidget(self.table, 2)
        row = QHBoxLayout()
        for text, slot in ((tr("New user"), self._new), (tr("Change type"), self._role),
                           (tr("Enable/Disable"), self._toggle), (tr("Reset password"), self._password),
                           (tr("Set quota"), self._quota), (tr("Delete"), self._delete), (tr("Refresh"), self.refresh)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(QLabel(f"<h3>{tr('Recent activity')}</h3>"))
        self.events = _table([tr("When"), tr("User"), tr("Action"), tr("Detail")], selectable=False)
        lay.addWidget(self.events, 2)
        self.status = QLabel("")
        lay.addWidget(self.status)
        self.refresh()

    def _current(self) -> Optional[Dict[str, Any]]:
        r = self.table.currentRow()
        return self.users[r] if 0 <= r < len(self.users) else None

    def _fail(self, e: Exception) -> None:
        QMessageBox.warning(self, tr("Error"), tr_error(e))

    def refresh(self) -> None:
        if not self.session.online:
            snap = self.session.store.users_snapshot()
            self.status.setText(tr("Offline: list saved locally on {when}.", when=fmt_time(snap["saved"]))
                                if snap["saved"] else tr("Offline: no saved list."))
            self._fill(snap["users"], [])
            return
        self.status.setText(tr("Loading..."))

        def done(res: Tuple[list, list]) -> None:
            users, events = res
            self.session.store.save_users_snapshot(users)
            self.status.setText(tr("{n} users", n=len(users)))
            self._fill(users, events)

        run_async(self, lambda: (self.session.client.users(), self.session.client.events(100)), done,
                  lambda e: self.status.setText(tr("Error: {msg}", msg=tr_error(e))))

    def _fill(self, users: List[Dict[str, Any]], events: List[Dict[str, Any]]) -> None:
        self.users = users
        self.table.setRowCount(len(users))
        for i, u in enumerate(users):
            vals = [u["username"], u.get("full_name", ""), role_label(u["role"]),
                    tr("Active") if u["active"] else tr("Disabled"), fmt_time(u["created"]), fmt_time(u["last_login"])]
            for j, v in enumerate(vals):
                self.table.setItem(i, j, QTableWidgetItem(v))
        self.events.setRowCount(len(events))
        for i, e in enumerate(events):
            vals = [fmt_time(e["ts"]), e["username"], e["action"], " ".join(x for x in (e.get("area") or "", e.get("path") or "") if x)]
            for j, v in enumerate(vals):
                self.events.setItem(i, j, QTableWidgetItem(v))

    def _guard(self) -> Optional[Dict[str, Any]]:
        if not self.session.can("users.manage"):
            QMessageBox.information(self, tr("Users"), tr("This operation is available only online as an administrator."))
            return None
        u = self._current()
        if u is None:
            QMessageBox.information(self, tr("Users"), tr("Select a user."))
        return u

    def _update(self, u: Dict[str, Any], done_text: str = "", **fields: Any) -> None:
        run_async(self, lambda: self.session.client.update_user(u["id"], **fields),
                  lambda _x: (self.refresh(), self.status.setText(done_text) if done_text else None), self._fail)

    def _new(self) -> None:
        if not self.session.can("users.manage"):
            return QMessageBox.information(self, tr("Users"), tr("This operation is available only online as an administrator."))
        dlg = NewUserDialog(self)
        if dlg.exec():
            n, p, r = dlg.values()
            run_async(self, lambda: self.session.client.create_user(n, p, r), lambda _x: self.refresh(), self._fail)

    def _role(self) -> None:
        u = self._guard()
        if u:
            new = ROLE_USER if u["role"] == ROLE_SERVER else ROLE_SERVER
            if QMessageBox.question(self, tr("Change type"), tr("Make {user} '{role}'?", user=u["username"], role=role_label(new))) \
                    == QMessageBox.StandardButton.Yes:
                self._update(u, role=new)

    def _toggle(self) -> None:
        u = self._guard()
        if u:
            self._update(u, active=not u["active"])

    def _password(self) -> None:
        u = self._guard()
        if u:
            pw, ok = QInputDialog.getText(self, tr("Reset password"), tr("New password for {user}:", user=u["username"]),
                                          QLineEdit.EchoMode.Password)
            if ok and pw:
                self._update(u, tr("Password updated."), password=pw)

    def _quota(self) -> None:
        u = self._guard()
        if u:
            mb, ok = QInputDialog.getInt(self, tr("Set quota"), tr("Personal folder quota for {user} (MB):", user=u["username"]),
                                         int(u.get("quota_mb", 0)), 1, 1 << 20)
            if ok:
                self._update(u, quota_mb=mb)

    def _delete(self) -> None:
        u = self._guard()
        if u and QMessageBox.question(self, tr("Delete"), tr("Delete user {user}? The files they uploaded stay on the server.",
                                                            user=u["username"])) == QMessageBox.StandardButton.Yes:
            run_async(self, lambda: self.session.client.delete_user(u["id"]), lambda _x: self.refresh(), self._fail)


class AdminHome(QWidget):
    """Administrator's main panel: Users, Database, Training in the foreground; metrological analysis
    is a secondary row with a single button."""

    def __init__(self, session: Session, on_training: Callable[[], None], on_analysis: Callable[[], None],
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<h2>{tr('Management')}</h2>"))
        self.tabs = QTabWidget()
        self.users = UserAdminWidget(session)
        self.db = ServerBrowserWidget(session)
        self.tabs.addTab(self.users, tr("Users"))
        self.tabs.addTab(self.db, tr("Database"))
        train = QWidget()
        tl = QVBoxLayout(train)
        tl.addWidget(QLabel(f"<h3>{tr('Training')}</h3>"))
        tl.addWidget(QLabel(tr("Train new YOLO models on the server datasets and publish them in the models folder.")))
        b = QPushButton(tr("Open the training page"))
        b.setMinimumHeight(48)
        b.clicked.connect(on_training)
        tl.addWidget(b)
        tl.addStretch(1)
        self.tabs.addTab(train, tr("Training"))
        self.tabs.currentChanged.connect(lambda i: (self.users.refresh, self.db.refresh)[i]() if i < 2 else None)
        lay.addWidget(self.tabs, 1)

        sec = QFrame()
        sec.setFrameShape(QFrame.Shape.StyledPanel)
        sl = QHBoxLayout(sec)
        sl.addWidget(QLabel(f"<b>{tr('Metrological analysis')}</b>"))
        btn = QPushButton(tr("Analysis"))
        btn.clicked.connect(on_analysis)
        sl.addWidget(btn)
        sl.addStretch(1)
        lay.addWidget(sec)
