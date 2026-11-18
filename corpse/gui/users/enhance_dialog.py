"""Improvement of a photo or a video, from the first click to the file on disk.

One window for the two ways of doing it: on this computer, when the models of `nautilus` and their libraries are
installed, or on the server, which keeps a queue and lets a computer with a graphics card do the work. The
questions are the same either way: which method, with which settings. Where the improved file should end up is
asked at the end instead, with the result on screen beside the original and the divider to compare the two,
because that is the moment when the answer is obvious.

The preview before starting works on a reduced copy (one frame, for a video): a few seconds, enough to choose.

Autore: Samuele Gallo
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMessageBox,
                               QProgressBar, QPushButton, QRadioButton, QVBoxLayout, QWidget)

from common import enhance_nautilus, image_enhance
from common.errors import AppError
from common.i18n import tr, tr_error
from common.ui.enhance_controls import BeforeAfter, ParamControls
from common.ui.qt_utils import run_async

from corpse.functions.users import enhance
from corpse.functions.users.session import Session

POLL_MS = 3000
PREVIEW_SIDE = 900                                      # the longest side of the picture the preview works on


def local_ready() -> bool:
    """Whether this computer can do the improvement by itself (the libraries are installed)."""
    return enhance_nautilus.possible() or bool(image_enhance.available())


def frame_of(media: Path) -> QImage:
    """The picture to work on: the photo itself, or the first frame of a video."""
    if image_enhance.is_video(media):
        from common.ui.label_editor import VideoSource
        source = VideoSource(media)
        try:
            return source.image(0)
        finally:
            source.close()
    return QImage(str(media))


class EnhanceDialog(QDialog):
    """Asks who does the work, with which method and where the result goes; then does it."""

    def __init__(self, session: Session, media: Path, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        self.media = Path(media)
        self.job: Dict[str, Any] = {}
        self.improved: Optional[Path] = None
        self.kept: Optional[Path] = None
        self.temp = Path(tempfile.mkdtemp(prefix="enhance_"))
        self.setWindowTitle(tr("Improve"))
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<b>{self.media.name}</b>"))

        # ---- who does the work ------------------------------------------
        who = QHBoxLayout()
        who.addWidget(QLabel(tr("Done by:")))
        self.here = QRadioButton(tr("This computer"))
        self.there = QRadioButton(tr("The server"))
        who.addWidget(self.here)
        who.addWidget(self.there)
        who.addStretch(1)
        lay.addLayout(who)
        self.here.setEnabled(local_ready())
        self.there.setEnabled(bool(getattr(session, "online", False)))
        self.here.setChecked(self.here.isEnabled())
        self.there.setChecked(not self.here.isChecked() and self.there.isEnabled())
        self.here.toggled.connect(self._mode_changed)

        # ---- method and its settings ------------------------------------
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Method:")))
        self.methods = QComboBox()
        self.methods.currentIndexChanged.connect(self._method_changed)
        row.addWidget(self.methods, 1)
        lay.addLayout(row)
        self.about = QLabel("")
        self.about.setWordWrap(True)
        self.about.setStyleSheet("color: palette(mid);")
        lay.addWidget(self.about)
        self.params = ParamControls()
        lay.addWidget(self.params)

        # ---- before and after -------------------------------------------
        self.preview = BeforeAfter()
        lay.addWidget(self.preview, 1)
        preview_row = QHBoxLayout()
        self.btn_preview = QPushButton(tr("Preview"))
        self.btn_preview.clicked.connect(self._preview)
        preview_row.addWidget(self.btn_preview)
        preview_row.addStretch(1)
        lay.addLayout(preview_row)

        # ---- where it ends up: asked once the improved file is there -----
        self.choice = QWidget()
        choice_lay = QVBoxLayout(self.choice)
        choice_lay.setContentsMargins(0, 0, 0, 0)
        choice_lay.addWidget(QLabel(tr("What do you want to do with the improved file?")))
        self.add = QRadioButton(tr("Add it beside the original (enhanced folder)"))
        self.add.setChecked(True)
        self.replace = QRadioButton(tr("Put it in place of the original (a copy stays in 'originals')"))
        choice_lay.addWidget(self.add)
        choice_lay.addWidget(self.replace)
        self.choice.setVisible(False)
        lay.addWidget(self.choice)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setVisible(False)
        lay.addWidget(self.bar)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.btn_go = QPushButton(tr("Improve"))
        self.btn_go.setDefault(True)
        self.btn_go.clicked.connect(self._start)
        buttons.addWidget(self.btn_go)
        self.btn_keep = QPushButton(tr("Keep"))              # appears with the result, not before
        self.btn_keep.setDefault(True)
        self.btn_keep.setVisible(False)
        self.btn_keep.clicked.connect(self._keep)
        buttons.addWidget(self.btn_keep)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.buttons.rejected.connect(self._cancel)
        buttons.addWidget(self.buttons)
        lay.addLayout(buttons)

        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self._poll)
        QTimer.singleShot(0, self._load_methods)

    # ---- the methods ---------------------------------------------------
    def _load_methods(self) -> None:
        """The models are imported here, not when the application starts: they bring PyTorch with them."""
        if not self.here.isChecked():
            return self._mode_changed()
        if enhance_nautilus.possible() and not image_enhance.available():
            self.status.setText(tr("Preparing the models..."))
            self.bar.setVisible(True)
            run_async(self, enhance_nautilus.install, lambda _names: self._methods_ready(), self._fail)
            return
        self._methods_ready()

    def _methods_ready(self) -> None:
        self.bar.setVisible(False)
        self.status.setText("")
        self.methods.clear()
        video = image_enhance.is_video(self.media)
        usable: List[image_enhance.Method] = []
        for method in image_enhance.methods():
            problem = method.problem or ("" if method.video or not video else tr("does not do videos"))
            title = method.title if not problem else f"{method.title} - {problem}"
            self.methods.addItem(title, method.name)
            index = self.methods.count() - 1
            self.methods.model().item(index).setEnabled(not problem)     # shown, but greyed out
            if not problem:
                usable.append(method)
        if usable:
            self.methods.setCurrentIndex([m.name for m in image_enhance.methods()].index(usable[0].name))
        else:
            self.status.setText(tr("No improvement is installed on this computer."))
        where = enhance_nautilus.device_name()
        if where:
            self.here.setText(tr("This computer ({device})", device=where))
        self._method_changed()

    def _current(self) -> Optional[image_enhance.Method]:
        name = self.methods.currentData()
        try:
            return image_enhance.method(name) if name else None
        except LookupError:
            return None

    def _method_changed(self) -> None:
        method = self._current()
        self.about.setText(method.description if method else "")
        self.params.set_params(method.params if method else ())
        self.preview.clear()
        self.btn_go.setEnabled(bool(method and method.usable) or self.there.isChecked())

    def _mode_changed(self) -> None:
        """On the server the method and the settings belong to the computer that does the work."""
        local = self.here.isChecked()
        for widget in (self.methods, self.params, self.btn_preview):
            widget.setEnabled(local)
        if local:
            self._load_methods()
        else:
            self.about.setText(tr("The server chooses the method of the computer that does the work."))
            self.preview.clear()
            self.btn_go.setEnabled(True)

    # ---- the preview ---------------------------------------------------
    def _preview(self) -> None:
        method = self._current()
        if method is None:
            return
        self.status.setText(tr("Preview..."))
        self.bar.setVisible(True)
        self.btn_preview.setEnabled(False)
        values = self.params.values()
        run_async(self, lambda: self._make_preview(method.name, values), self._preview_ready, self._fail)

    def _make_preview(self, method: str, values: Dict[str, Any]):
        """A reduced copy is improved instead of the whole file: seconds instead of minutes."""
        image = frame_of(self.media)
        if image.isNull():
            raise AppError("Cannot read this file.")
        small = image.scaled(PREVIEW_SIDE, PREVIEW_SIDE, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        before = self.temp / "before.png"
        small.save(str(before))
        after = image_enhance.improve(before, method, replace=True, params=values,
                                      dest=self.temp / "after.png")
        return small, QImage(str(after))

    def _preview_ready(self, images) -> None:
        self.bar.setVisible(False)
        self.btn_preview.setEnabled(True)
        self.status.setText(tr("Drag the divider to compare."))
        self.preview.set_images(*images)

    # ---- doing it -------------------------------------------------------
    def _start(self) -> None:
        self.btn_go.setEnabled(False)
        self.bar.setVisible(True)
        if self.here.isChecked():
            method = self._current()
            if method is None:
                return self._fail(AppError("Choose a method."))
            self.status.setText(tr("Working on it..."))
            values = self.params.values()
            run_async(self, lambda: self._run_here(method.name, values), self._ready, self._fail)
            return
        self.status.setText(tr("Sending the file..."))
        run_async(self, lambda: enhance.send(self.session.client, self.media), self._sent, self._fail)

    def _run_here(self, method: str, values: Dict[str, Any]) -> Path:
        name = image_enhance.enhanced_path(self.media).name
        return image_enhance.improve(self.media, method, replace=True, params=values, dest=self.temp / name)

    # ---- doing it on the server -----------------------------------------
    def _sent(self, job: Dict[str, Any]) -> None:
        self.job = job
        self.status.setText(tr("Waiting for a computer that can do it..."))
        self.timer.start()

    def _poll(self) -> None:
        if not self.job:
            return
        self.timer.stop()
        run_async(self, lambda: enhance.state(self.session.client, self.job), self._state, self._fail)

    def _state(self, job: Dict[str, Any]) -> None:
        self.job = job
        if enhance.done(job):
            self.status.setText(tr("Bringing the improved file back..."))
            run_async(self, lambda: enhance.collect(self.session.client, self.job, self.temp),
                      self._ready, self._fail)
            return
        if enhance.failed(job):
            self.bar.setVisible(False)
            self.btn_go.setEnabled(True)
            return self.status.setText(tr("The improvement did not work: {msg}", msg=job.get("message", "")))
        if not enhance.waiting(job):
            return self._fail(AppError("The improvement was cancelled."))
        self.status.setText(tr("Working on it...") if job.get("status") == "running"
                            else tr("Waiting for a computer that can do it..."))
        self.timer.start()

    # ---- the file ------------------------------------------------------
    def _ready(self, improved: Path) -> None:
        """The improved file is here: it is shown beside the original, and only now comes the question of where
        it should end up."""
        self.improved = Path(improved)
        self.bar.setVisible(False)
        self.status.setText(tr("The improved file is ready."))
        self.preview.set_images(self._shrink(self.media), self._shrink(self.improved))
        self.choice.setVisible(True)
        self.btn_go.setVisible(False)
        self.btn_keep.setVisible(True)
        self.btn_keep.setFocus()
        self.btn_preview.setEnabled(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Not now"))

    def _shrink(self, media: Path) -> QImage:
        """The picture at a size that fits the window (one frame, for a video)."""
        image = frame_of(media)
        if image.isNull():
            return image
        return image.scaled(PREVIEW_SIDE, PREVIEW_SIDE, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)

    def _keep(self) -> None:
        """What the user chose, now that the improved file is on screen."""
        if self.improved is None:
            return
        how = enhance.REPLACE if self.replace.isChecked() else enhance.ADD
        try:
            self.kept = enhance.keep(self.media, self.improved, how)
        except OSError as e:
            return self._fail(e)
        if self.job:
            enhance.cleanup(self.session.client, self.job)
        self.accept()

    def _fail(self, error: Exception) -> None:
        self.timer.stop()
        self.bar.setVisible(False)
        self.btn_go.setVisible(True)
        self.btn_go.setEnabled(True)
        self.btn_keep.setVisible(False)
        self.btn_preview.setEnabled(self.here.isChecked())
        self.status.setText(tr_error(error) if isinstance(error, AppError) else str(error))

    def _cancel(self) -> None:
        self.timer.stop()
        if self.job and enhance.waiting(self.job):
            try:
                self.session.client.cancel_enhance(self.job["id"])
            except Exception:                              # noqa: BLE001 - already started: it simply goes on
                pass
        self.reject()


def improve_media(parent: Optional[QWidget], session: Session, media: Path) -> Optional[Path]:
    """Opens the window; returns the file that was kept, or None."""
    if not local_ready() and not getattr(session, "online", False):
        QMessageBox.information(parent, tr("Improve"),
                                tr("Install the improvement on this computer, or connect to the server."))
        return None
    dialog = EnhanceDialog(session, Path(media), parent)
    return dialog.kept if dialog.exec() == QDialog.DialogCode.Accepted else None


improve_with_server = improve_media            # the old name, kept for whoever still calls it
