"""Work groups: the list of yours, their shared folder, the members and what is waiting for approval.

Anybody can make a group and is then its administrator. The administrators choose the members, promote them and
approve what the others send; a member sees and downloads everything, and what they send waits in the group's
quarantine until an administrator accepts it.

Autore: Samuele Gallo
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTabWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from common.format import fmt_size, fmt_time
from common.i18n import tr, tr_error
from common.params import AREA_GROUPS, GROUP_ADMIN
from common.ui.qt_utils import run_async
from common.ui.server_state import server_note, server_ready

from corpse.functions.users.session import Session
from .browser import ServerBrowserWidget


def role_name(role: str) -> str:
    return tr("Administrator of the group") if role == GROUP_ADMIN else tr("Member")


class MembersWidget(QWidget):
    """Who is in the group and what they may do. Only an administrator of the group can change this."""

    def __init__(self, session: Session, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        self.group: Dict[str, Any] = {}
        lay = QVBoxLayout(self)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([tr("User"), tr("Role")])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.pick = QComboBox()
        self.pick.setEditable(True)
        self.pick.setToolTip(tr("Name of the user to add"))
        self.btn_add = self._button(row, tr("Add"), self._add, first=self.pick)
        self.btn_promote = self._button(row, tr("Make administrator"), lambda: self._role(GROUP_ADMIN))
        self.btn_demote = self._button(row, tr("Back to member"), lambda: self._role("member"))
        self.btn_remove = self._button(row, tr("Remove"), self._remove)
        row.addStretch(1)
        self.btn_leave = self._button(row, tr("Leave the group"), self._leave)
        lay.addLayout(row)
        self.status = QLabel("")
        lay.addWidget(self.status)

    def _button(self, row: QHBoxLayout, text: str, slot, first: Optional[QWidget] = None) -> QPushButton:
        if first is not None:
            row.addWidget(first, 1)
        b = QPushButton(text)
        b.clicked.connect(slot)
        row.addWidget(b)
        return b

    def show_group(self, group: Dict[str, Any], users: List[str]) -> None:
        self.group = group
        members = group.get("members", [])
        self.table.setRowCount(len(members))
        for i, m in enumerate(members):
            self.table.setItem(i, 0, QTableWidgetItem(m["username"]))
            self.table.setItem(i, 1, QTableWidgetItem(role_name(m["role"])))
        names = {m["username"] for m in members}
        self.pick.clear()
        self.pick.addItems([u for u in users if u not in names])
        boss = group.get("role") == GROUP_ADMIN or self.session.can("groups.manage")
        for b in (self.btn_add, self.btn_promote, self.btn_demote, self.btn_remove):
            b.setEnabled(boss)
        self.pick.setEnabled(boss)
        self.btn_leave.setEnabled(bool(group.get("role")))
        self.status.setText("" if boss else tr("Only an administrator of the group can do this."))

    def _chosen(self) -> str:
        r = self.table.currentRow()
        item = self.table.item(r, 0) if r >= 0 else None
        return item.text() if item else ""

    def _call(self, work) -> None:
        run_async(self, work, lambda _r: self.parent_refresh(),
                  lambda e: QMessageBox.warning(self, tr("Work groups"), tr_error(e)))

    def parent_refresh(self) -> None:
        page = self.parent()
        while page is not None and not isinstance(page, GroupsPage):
            page = page.parent()
        if page is not None:
            page.refresh()

    def _add(self) -> None:
        who = self.pick.currentText().strip()
        if who and self.group:
            self._call(lambda: self.session.client.set_member(self.group["name"], who, True))

    def _role(self, role: str) -> None:
        who = self._chosen()
        if who and self.group:
            self._call(lambda: self.session.client.set_group_role(self.group["name"], who, role))

    def _remove(self) -> None:
        who = self._chosen()
        if who and self.group:
            self._call(lambda: self.session.client.set_member(self.group["name"], who, False))

    def _leave(self) -> None:
        if not self.group:
            return
        if QMessageBox.question(self, tr("Work groups"),
                                tr("Leave the group {name}?", name=self.group["name"])) \
                == QMessageBox.StandardButton.Yes:
            self._call(lambda: self.session.client.leave_group(self.group["name"]))


class PendingWidget(QWidget):
    """What the members sent and is waiting: an administrator of the group accepts it or throws it away."""

    def __init__(self, session: Session, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        self.group: Dict[str, Any] = {}
        self.waiting: List[Dict[str, Any]] = []
        lay = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([tr("File"), tr("Sent by"), tr("Size"), tr("Sent on")])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.btn_approve = QPushButton(tr("Approve"))
        self.btn_approve.clicked.connect(lambda: self._decide(True))
        self.btn_reject = QPushButton(tr("Reject"))
        self.btn_reject.clicked.connect(lambda: self._decide(False))
        row.addWidget(self.btn_approve)
        row.addWidget(self.btn_reject)
        row.addStretch(1)
        lay.addLayout(row)
        self.status = QLabel("")
        lay.addWidget(self.status)

    def show_group(self, group: Dict[str, Any]) -> None:
        self.group = group
        boss = group.get("role") == GROUP_ADMIN or self.session.can("groups.manage")
        for b in (self.btn_approve, self.btn_reject):
            b.setEnabled(boss)
        self.table.setRowCount(0)
        if not boss:
            self.status.setText(tr("Only an administrator of the group can do this."))
            return
        self.status.setText(tr("Loading..."))
        run_async(self, lambda: self.session.client.group_pending(group["name"]), self._fill,
                  lambda e: self.status.setText(tr("Error: {msg}", msg=tr_error(e))))

    def _fill(self, waiting: List[Dict[str, Any]]) -> None:
        self.waiting = waiting
        self.table.setRowCount(len(waiting))
        for i, w in enumerate(waiting):
            for c, v in enumerate((w["path"], w["sender"], fmt_size(w["size"]), fmt_time(w["sent"]))):
                self.table.setItem(i, c, QTableWidgetItem(str(v)))
        self.status.setText(tr("{n} files waiting", n=len(waiting)))

    def _decide(self, approve: bool) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        chosen = [self.waiting[r] for r in rows if 0 <= r < len(self.waiting)]
        if not chosen:
            return QMessageBox.information(self, tr("Work groups"), tr("Select a file."))
        if not approve and QMessageBox.question(
                self, tr("Work groups"),
                tr("Reject and permanently delete {n} files?", n=len(chosen))) != QMessageBox.StandardButton.Yes:
            return
        client = self.session.client

        def work():
            for w in chosen:
                if approve:
                    client.approve_group_upload(w["logical"])
                else:
                    client.reject_group_upload(w["logical"])
            return len(chosen)

        run_async(self, work, lambda _n: self.show_group(self.group),
                  lambda e: QMessageBox.warning(self, tr("Work groups"), tr_error(e)))


class DeleteGroupDialog(QDialog):
    """Deleting a group cannot be undone, so it is confirmed by writing its name."""

    def __init__(self, group: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.group = group
        self.setWindowTitle(tr("Delete group"))
        lay = QVBoxLayout(self)
        text = QLabel(tr("The group {name} will be deleted and its members will lose access to the shared folder. "
                         "This cannot be undone.", name=group))
        text.setWordWrap(True)
        lay.addWidget(text)
        self.files = QCheckBox(tr("Also delete the files of the group from the server"))
        lay.addWidget(self.files)
        lay.addWidget(QLabel(tr("Write the name of the group to confirm:")))
        self.typed = QLineEdit()
        self.typed.setPlaceholderText(group)
        self.typed.textChanged.connect(self._check)
        lay.addWidget(self.typed)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Delete group"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self._check("")

    def _check(self, text: str) -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            text.strip().lower() == self.group.strip().lower())

    def delete_files(self) -> bool:
        return self.files.isChecked()


class GroupSettingsWidget(QWidget):
    """Settings of a group: what it is for, how the members send files, and deleting the group."""

    def __init__(self, session: Session, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        self.group: Dict[str, Any] = {}
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("What the group is for:")))
        self.description = QPlainTextEdit()
        self.description.setPlaceholderText(tr("A few words that the members see."))
        self.description.setFixedHeight(80)
        lay.addWidget(self.description)
        self.free_upload = QCheckBox(tr("The members can add files without approval"))
        self.free_upload.setToolTip(tr("Off: what a member sends waits for an administrator of the group."))
        lay.addWidget(self.free_upload)
        row = QHBoxLayout()
        self.btn_save = QPushButton(tr("Save"))
        self.btn_save.clicked.connect(self._save)
        row.addWidget(self.btn_save)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addSpacing(16)
        danger = QLabel(f"<b>{tr('Delete group')}</b>")
        lay.addWidget(danger)
        self.danger_note = QLabel(tr("The group disappears for everybody. You can also delete its files."))
        self.danger_note.setWordWrap(True)
        lay.addWidget(self.danger_note)
        self.btn_delete = QPushButton(tr("Delete group..."))
        self.btn_delete.clicked.connect(self._delete)
        lay.addWidget(self.btn_delete, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addStretch(1)
        self.status = QLabel("")
        lay.addWidget(self.status)

    def show_group(self, group: Dict[str, Any]) -> None:
        self.group = group
        self.description.setPlainText(group.get("description", ""))
        self.free_upload.setChecked(bool(group.get("free_upload")))
        boss = group.get("role") == GROUP_ADMIN or self.session.can("groups.manage")
        for w in (self.description, self.free_upload, self.btn_save, self.btn_delete):
            w.setEnabled(boss)
        self.status.setText("" if boss else tr("Only an administrator of the group can do this."))

    def _page(self) -> Optional["GroupsPage"]:
        page = self.parent()
        while page is not None and not isinstance(page, GroupsPage):
            page = page.parent()
        return page

    def _done(self, _result: Any) -> None:
        page = self._page()
        if page is not None:
            page.refresh()

    def _fail(self, e: Exception) -> None:
        QMessageBox.warning(self, tr("Work groups"), tr_error(e))

    def _save(self) -> None:
        if not self.group:
            return
        name = self.group["name"]
        text, free = self.description.toPlainText(), self.free_upload.isChecked()
        run_async(self, lambda: self.session.client.update_group(name, text, free), self._done, self._fail)

    def _delete(self) -> None:
        if not self.group:
            return
        name = self.group["name"]
        dialog = DeleteGroupDialog(name, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        files = dialog.delete_files()
        run_async(self, lambda: self.session.client.delete_group(name, files), self._done, self._fail)


class GroupsPage(QWidget):
    """The groups of the user: the list on the left, and on the right the folder, the members and what is waiting."""

    def __init__(self, session: Session, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        self.groups: List[Dict[str, Any]] = []
        self.users: List[str] = []
        lay = QVBoxLayout(self)
        head = QHBoxLayout()
        head.addWidget(QLabel(f"<h3>{tr('Work groups')}</h3>"), 1)
        self.btn_new = QPushButton(tr("New group"))
        self.btn_new.clicked.connect(self._new)
        self.btn_refresh = QPushButton(tr("Refresh"))
        self.btn_refresh.clicked.connect(self.refresh)
        for b in (self.btn_new, self.btn_refresh):
            head.addWidget(b)
        lay.addLayout(head)
        hint = QLabel(tr("Every group has a shared folder on the server, open to its members only."))
        hint.setWordWrap(True)
        lay.addWidget(hint)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(lambda _i: self._show_current())
        split.addWidget(self.list)
        self.tabs = QTabWidget()
        self.files = ServerBrowserWidget(session, (AREA_GROUPS,))
        self.members = MembersWidget(session)
        self.pending = PendingWidget(session)
        self.settings = GroupSettingsWidget(session)
        self.tabs.addTab(self.files, tr("Files"))
        self.tabs.addTab(self.members, tr("Members"))
        self.tabs.addTab(self.pending, tr("Waiting"))
        self.tabs.addTab(self.settings, tr("Settings"))
        split.addWidget(self.tabs)
        split.setSizes([220, 760])
        lay.addWidget(split, 1)
        self.status = QLabel("")
        lay.addWidget(self.status)
        self.refresh()

    # ---- data -----------------------------------------------------------
    def _online(self) -> bool:
        return server_ready(self.session)

    def refresh(self) -> None:
        self.btn_new.setEnabled(self._online())
        if not self._online():
            self.status.setText(server_note(self.session))
            return
        self.status.setText(tr("Loading..."))
        run_async(self, self._load, self._fill,
                  lambda e: self.status.setText(tr("Error: {msg}", msg=tr_error(e))))

    def _load(self):
        client = self.session.client
        users: List[str] = []
        if self.session.can("users.manage"):
            users = [u["username"] for u in client.users()]
        return client.groups(everyone=self.session.can("groups.manage")), users

    def _fill(self, res) -> None:
        groups, users = res
        self.groups, self.users = groups, users
        keep = self.list.currentRow()
        self.list.clear()
        for g in groups:
            item = QListWidgetItem(g["name"] if g.get("role") != GROUP_ADMIN else f"{g['name']} ★")
            item.setToolTip(role_name(g.get("role", "")) if g.get("role") else "")
            self.list.addItem(item)
        if groups:
            self.list.setCurrentRow(min(max(0, keep), len(groups) - 1))
        self.status.setText(tr("{n} groups", n=len(groups)) if groups
                            else tr("You are not in any group yet: make one with 'New group'."))
        self._show_current()

    def current(self) -> Optional[Dict[str, Any]]:
        r = self.list.currentRow()
        return self.groups[r] if 0 <= r < len(self.groups) else None

    def _show_current(self) -> None:
        group = self.current()
        if group is None:
            self.members.show_group({}, [])
            self.settings.show_group({})
            return
        users = self.users or [m["username"] for m in group.get("members", [])]
        self.members.show_group(group, users)
        self.pending.show_group(group)
        self.settings.show_group(group)
        self.files._goto(AREA_GROUPS, group["name"])     # the tree starts inside the group

    # ---- actions ---------------------------------------------------------
    def _fail(self, e: Exception) -> None:
        QMessageBox.warning(self, tr("Work groups"), tr_error(e))

    def _new(self) -> None:
        name, ok = QInputDialog.getText(self, tr("New group"), tr("Name of the group"))
        if ok and name.strip():
            run_async(self, lambda: self.session.client.create_group(name.strip()),
                      lambda _g: self.refresh(), self._fail)
