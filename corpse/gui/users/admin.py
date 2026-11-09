"""User management and the administrator's main panel (users, database, training; analysis in the background)."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QTabBar,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from common.format import fmt_time
from common.i18n import tr, tr_error
from common.params import AREAS_SHARED, ROLE_SERVER, ROLE_USER, SUBMISSION_PENDING
from common.ui.qt_utils import run_async

from corpse.functions.users.session import Session
from .browser import ServerBrowserWidget
from .labels import role_label, status_label
from .preview_dialog import PreviewDialog


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


class SubmissionsWidget(QWidget):
    """What the users have sent, of one kind (photos, datasets or models): approve (it is published) or reject (it is deleted)."""

    def __init__(self, session: Session, kind: str = "photos", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        self.kind = kind
        self.items: List[Dict[str, Any]] = []
        self.title, subject, count = {
            "photos": (tr("Photo review"), tr("Species"), tr("Photos")),
            "stereo": (tr("Stereo photo review"), tr("Species"), tr("Photos")),
            "video": (tr("Video review"), tr("Species"), tr("Videos")),
            "dataset": (tr("Dataset review"), tr("Dataset"), tr("Images")),
            "model": (tr("Model review"), tr("Species"), ""),
        }[kind]
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<h3>{self.title}</h3>"))
        self.table = _table([tr("User"), subject, count, tr("Sent"), tr("Status")])
        self.table.setColumnHidden(2, kind == "model")           # a model is a single file: no count
        lay.addWidget(self.table, 1)
        self.btn_preview, self.btn_approve, self.btn_reject, self.btn_refresh = (QPushButton(t) for t in (
            tr("Preview"), tr("Approve"), tr("Reject"), tr("Refresh")))
        row = QHBoxLayout()
        for button, slot in ((self.btn_preview, self._preview), (self.btn_approve, self._approve),
                             (self.btn_reject, self._reject), (self.btn_refresh, self.refresh)):
            button.clicked.connect(slot)
            row.addWidget(button)
        row.addStretch(1)
        lay.addLayout(row)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.status = QLabel("")
        lay.addWidget(self.status)
        self.refresh()

    def _current(self) -> Optional[Dict[str, Any]]:
        r = self.table.currentRow()
        return self.items[r] if 0 <= r < len(self.items) else None
    
    def _update_buttons(self) -> None:
        """Approve and Reject only make sense for a submission still waiting: for a decided one they disappear."""
        s = self._current()
        waiting = s is None or s["status"] == SUBMISSION_PENDING
        self.btn_approve.setVisible(waiting)
        self.btn_reject.setVisible(waiting)

    def _fail(self, e: Exception) -> None:
        QMessageBox.warning(self, tr("Error"), tr_error(e))

    def refresh(self) -> None:
        if not self.session.online:
            self._fill([])
            return
        self.status.setText(tr("Loading..."))

        def done(items: List[Dict[str, Any]]) -> None:
            self._fill(items)
            self.status.setText(tr("{n} submissions", n=len(items)))

        run_async(self, lambda: self.session.client.species_submissions(kind=self.kind), done,
                  lambda e: self.status.setText(tr("Error: {msg}", msg=tr_error(e))))

    def _fill(self, items: List[Dict[str, Any]]) -> None:
        self.items = items
        self.table.setRowCount(len(items))
        for i, s in enumerate(items):
            vals = [s["username"], s["species"], str(s["photos"]), fmt_time(s["created"]), status_label(s["status"])]
            for j, v in enumerate(vals):
                self.table.setItem(i, j, QTableWidgetItem(v))
        self._update_buttons()

    def _pending(self) -> Optional[Dict[str, Any]]:
        """The selected submission, if the administrator can and should review it; otherwise explains why not."""
        if not self.session.can("species.review"):
            QMessageBox.information(self, self.title,
                                    tr("This operation is available only online as an administrator."))
            return None
        s = self._current()
        if s is None or s["status"] != SUBMISSION_PENDING:
            QMessageBox.information(self, self.title, tr("Select a submission waiting for review."))
            return None
        return s

    def _confirm(self, text: str) -> bool:
        return QMessageBox.question(self, self.title, text) == QMessageBox.StandardButton.Yes

    def _question(self, s: Dict[str, Any], approve: bool) -> str:
        n, name, user = s["photos"], s["species"], s["username"]
        if self.kind == "dataset":
            if approve:
                return tr("Approve the dataset {name} ({n} images) sent by {user}?", name=name, n=n, user=user)
            return tr("Reject and permanently delete the dataset {name} ({n} images) sent by {user}?", name=name, n=n, user=user)
        if self.kind == "model":
            if approve:
                return tr("Approve the model of {species} sent by {user}?", species=name, user=user)
            return tr("Reject and permanently delete the model of {species} sent by {user}?", species=name, user=user)
        if self.kind == "video":
            if approve:
                return tr("Approve the {n} videos of {species} sent by {user}?", n=n, species=name, user=user)
            return tr("Reject and permanently delete the {n} videos of {species} sent by {user}?", n=n, species=name, user=user)
        if approve:
            return tr("Approve the {n} photos of {species} sent by {user}?", n=n, species=name, user=user)
        return tr("Reject and permanently delete the {n} photos of {species} sent by {user}?", n=n, species=name, user=user)

    def _run(self, call: Callable[[], Any]) -> None:
        run_async(self, call, lambda _x: self.refresh(), self._fail)

    def _approve(self) -> None:
        s = self._pending()
        if s and self._confirm(self._question(s, True)):
            self._run(lambda: self.session.client.approve_submission(s["id"]))

    def _preview(self) -> None:
        s = self._current()
        if s is None:
            QMessageBox.information(self, self.title, tr("Select a submission waiting for review."))
            return
        PreviewDialog(self.session.client, self.kind, s, self).exec()

    def _reject(self) -> None:
        s = self._pending()
        if s and self._confirm(self._question(s, False)):
            self._run(lambda: self.session.client.reject_submission(s["id"]))

class ReviewWidget(QWidget):
    """What the users have sent and is waiting for approval: photos, datasets and models, one tab each."""

    def __init__(self, session: Session, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.photos = SubmissionsWidget(session, "photos")
        self.stereo = SubmissionsWidget(session, "stereo")
        self.videos = SubmissionsWidget(session, "video")
        self.datasets = SubmissionsWidget(session, "dataset")
        self.models = SubmissionsWidget(session, "model")
        self.tabs = QTabWidget()
        self.tabs.addTab(self.photos, tr("Photos"))
        self.tabs.addTab(self.stereo, tr("Stereo photos"))
        self.tabs.addTab(self.videos, tr("Videos"))
        self.tabs.addTab(self.datasets, tr("Datasets"))
        self.tabs.addTab(self.models, tr("YOLO models"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.tabs)

    def refresh(self) -> None:
        for w in (self.photos, self.stereo, self.videos, self.datasets, self.models):
            w.refresh()

class AdminHome(QWidget):
    """Administrator's main panel: Users, Database, Training in the foreground; metrological analysis
    is a secondary row with a single button."""

    def __init__(self, session: Session, on_training: Callable[[], None], on_analysis: Callable[[], None],
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        self.session = session
        lay.addWidget(QLabel(f"<h2>{tr('Management')}</h2>"))
        self.banner = QLabel(tr("The server is unreachable: you are working locally only. Users and server folders "
                                "are available again after you reconnect."))
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet("background: #ffe0b2; color: #4e342e; border-radius: 6px; padding: 8px;")
        lay.addWidget(self.banner)
        self.tabs = QTabWidget()
        self.users = UserAdminWidget(session)
        self.db = ServerBrowserWidget(session, AREAS_SHARED)
        self.review = ReviewWidget(session)
        train = QWidget()
        tl = QVBoxLayout(train)
        tl.addWidget(QLabel(f"<h3>{tr('Training')}</h3>"))
        tl.addWidget(QLabel(tr("Train new YOLO models on the server datasets and publish them in the models folder.")))
        b = QPushButton(tr("Open the training page"))
        b.setMinimumHeight(48)
        b.clicked.connect(on_training)
        tl.addWidget(b)
        tl.addStretch(1)
        self.server_tabs = (self.tabs.addTab(self.users, tr("Users")),
                            self.tabs.addTab(self.db, tr("Database")),
                            self.tabs.addTab(self.review, tr("Review")))
        self.local_tab = self.tabs.addTab(train, tr("Training"))
        refreshers = (self.users.refresh, self.db.refresh, self.review.refresh)
        self.tabs.currentChanged.connect(lambda i: refreshers[i]() if i < len(refreshers) else None)
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
        self._lock_tabs()

    def _lock_tabs(self) -> None:
        """Offline: only the local work (training, analysis) is offered; the server tabs are disabled."""
        online = self.session.online
        self.banner.setVisible(not online)
        for i in self.server_tabs:
            self.tabs.setTabEnabled(i, online)
        if not online:
            self.tabs.setCurrentIndex(self.local_tab)

    def apply_state(self) -> None:
        """Called after a reconnect: the server tabs come back and are reloaded."""
        self._lock_tabs()
        if self.session.online:
            self.users.refresh()
            self.db.refresh()
            self.review.refresh()
