"""How the models behave: what the training measured, and what they do on real photos.

Two things are shown side by side. The numbers of the training come from the model's own `.json`, and say how it
did on its own validation images — useful, but every model was measured on different photos. So the same models can
also be tried on the approved photos of a species that carry labels: the same photos for everybody, which is the
only honest way of saying that one model is better than another.
"""
from __future__ import annotations

import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                               QProgressBar, QPushButton, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem,
                               QTextEdit, QVBoxLayout, QWidget)

from common.i18n import tr, tr_error
from common.model_metadata import fetch_remote_metadata
from common.params import IMAGE_SUFFIXES, KIND_AREA
from common.remote_tree import walk_remote
from common.ui.layout import fit_to_screen
from common.ui.qt_utils import run_async
from common.ui.server_state import server_note, server_ready

from corpse.functions.analysis.model_eval import Score, evaluate, yolo_detector
from corpse.gui.users.model_info import model_info_lines

MODELS_AREA = "models"
TEST_PHOTOS = 40                     # how many labelled photos the test uses by default
METRIC_KEYS = ("mAP50", "mAP50-95", "precision", "recall")


def metric(meta: Dict[str, Any], key: str) -> Optional[float]:
    value = (meta.get("metrics") or {}).get(key)
    return float(value) if isinstance(value, (int, float)) else None


def fmt(value: Optional[float]) -> str:
    return "-" if value is None else f"{value:.3f}"


def labelled_photos(client: Any, species: str, limit: int) -> List[Tuple[str, str]]:
    """(photo, its label file) of a species, among the approved photos that have labels."""
    pairs: List[Tuple[str, str]] = []
    labels = {}
    photos = []
    for rel, _size in walk_remote(client, KIND_AREA["photos"], species):
        suffix = PurePosixPath(rel).suffix.lower()
        if suffix == ".txt" and PurePosixPath(rel).name != "classes.txt":
            labels[str(PurePosixPath(rel).with_suffix(""))] = rel
        elif suffix in IMAGE_SUFFIXES:
            photos.append(rel)
    for rel in sorted(photos):
        if len(pairs) >= limit:
            break
        label = labels.get(str(PurePosixPath(rel).with_suffix("")))
        if label:
            pairs.append((rel, label))
    return pairs


class ModelPerformanceDialog(QDialog):
    """The models of the server with their numbers, and the test on real photos."""

    def __init__(self, session: Any, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.session = session
        self.items: List[Dict[str, Any]] = []
        self.meta: Dict[str, Dict[str, Any]] = {}            # path of the model -> its metadata
        self.setWindowTitle(tr("Performance of the models"))
        fit_to_screen(self, 980, 640)
        lay = QVBoxLayout(self)
        hint = QLabel(tr("The numbers of the training come from the images each model was validated on. The test "
                         "instead tries the chosen models on the same approved photos, the ones that carry labels."))
        hint.setWordWrap(True)
        lay.addWidget(hint)

        split = QSplitter(Qt.Orientation.Vertical)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([tr("Species"), tr("Model"), tr("mAP50"), tr("mAP50-95"),
                                              tr("Precision"), tr("Recall"), tr("Trained by")])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self._show_card)
        split.addWidget(self.table)
        self.card = QTextEdit()
        self.card.setReadOnly(True)
        split.addWidget(self.card)
        split.setSizes([400, 240])
        lay.addWidget(split, 1)

        row = QHBoxLayout()
        self.btn_test = QPushButton(tr("Try on real photos"))
        self.btn_test.clicked.connect(self._test)
        self.photos = QSpinBox()
        self.photos.setRange(1, 500)
        self.photos.setValue(TEST_PHOTOS)
        self.btn_refresh = QPushButton(tr("Refresh"))
        self.btn_refresh.clicked.connect(self.refresh)
        row.addWidget(self.btn_test)
        row.addWidget(QLabel(tr("Photos to use:")))
        row.addWidget(self.photos)
        row.addWidget(self.btn_refresh)
        row.addStretch(1)
        lay.addLayout(row)
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        lay.addWidget(self.bar)
        self.status = QLabel("")
        lay.addWidget(self.status)
        self.refresh()

    # ---- the models ----------------------------------------------------
    def _online(self) -> bool:
        return bool(self.session and server_ready(self.session))

    def refresh(self) -> None:
        self.btn_test.setEnabled(self._online())
        if not self._online():
            self.status.setText(tr("You are offline: the server folders are not available."))
            return
        self.status.setText(tr("Loading..."))
        run_async(self, self._load, self._fill, lambda e: self.status.setText(tr("Error: {msg}", msg=tr_error(e))))

    def _load(self) -> List[Dict[str, Any]]:
        client = self.session.client
        items = []
        for item in client.catalog("model"):
            meta = fetch_remote_metadata(client, MODELS_AREA, item["path"]) or {}
            items.append(dict(item, meta=meta))
        return items

    def _fill(self, items: List[Dict[str, Any]]) -> None:
        self.items = items
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(items))
        for i, item in enumerate(items):
            meta = item["meta"]
            values = [item.get("species", ""), PurePosixPath(item["path"]).name] + \
                     [fmt(metric(meta, k)) for k in METRIC_KEYS] + [meta.get("trained_by", item.get("uploader", ""))]
            for c, v in enumerate(values):
                cell = QTableWidgetItem(str(v))
                cell.setData(Qt.ItemDataRole.UserRole, item)
                self.table.setItem(i, c, cell)
        self.table.setSortingEnabled(True)
        self.status.setText(tr("{n} models", n=len(items)))
        self._show_card()

    def _selected(self) -> List[Dict[str, Any]]:
        rows = {i.row() for i in self.table.selectedIndexes()}
        out = []
        for r in sorted(rows):
            cell = self.table.item(r, 0)
            if cell is not None:
                out.append(cell.data(Qt.ItemDataRole.UserRole))
        return out

    def _show_card(self) -> None:
        chosen = self._selected()
        if not chosen:
            self.card.setPlainText(tr("Select one or more models."))
            return
        if len(chosen) == 1:
            item = chosen[0]
            lines = [PurePosixPath(item["path"]).name] + model_info_lines(item["meta"])
            self.card.setPlainText("\n".join(lines))
            return
        rows = [tr("Comparison of {n} models", n=len(chosen)), ""]
        for item in chosen:
            numbers = "  ".join(f"{k} {fmt(metric(item['meta'], k))}" for k in METRIC_KEYS)
            rows.append(f"{PurePosixPath(item['path']).name}: {numbers}")
        self.card.setPlainText("\n".join(rows))

    # ---- the test on real photos ---------------------------------------
    def _test(self) -> None:
        chosen = self._selected()
        if not chosen:
            return QMessageBox.information(self, tr("Performance of the models"), tr("Select one or more models."))
        species = {item.get("species", "") for item in chosen}
        if len(species) > 1 or not species or not next(iter(species)):
            return QMessageBox.information(self, tr("Performance of the models"),
                                           tr("Choose models of the same species: they are tried on its photos."))
        limit = self.photos.value()
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)
        self.btn_test.setEnabled(False)
        self.status.setText(tr("Loading..."))
        run_async(self, lambda: self._run_test(chosen, next(iter(species)), limit), self._show_test, self._test_failed)

    def _run_test(self, models: List[Dict[str, Any]], species: str, limit: int) -> List[Tuple[str, Score]]:
        client = self.session.client
        pairs = labelled_photos(client, species, limit)
        if not pairs:
            raise LookupError(tr("No labelled photo of {species} on the server.", species=species))
        results = []
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            photos: List[Tuple[Path, str]] = []
            for rel, label_rel in pairs:
                local = folder / PurePosixPath(rel).name
                client.download(KIND_AREA["photos"], rel, local)
                photos.append((local, client.read_bytes(KIND_AREA["photos"], label_rel).decode("utf-8", "replace")))
            for item in models:
                model_file = folder / PurePosixPath(item["path"]).name
                client.download(MODELS_AREA, item["path"], model_file)
                results.append((PurePosixPath(item["path"]).name,
                                evaluate(yolo_detector(model_file), photos)))
        return results

    def _show_test(self, results: List[Tuple[str, Score]]) -> None:
        self.bar.setVisible(False)
        self.btn_test.setEnabled(True)
        best = max(results, key=lambda r: r[1].f1)[0] if results else ""
        lines = [tr("Tried on {n} labelled photos of the server", n=results[0][1].photos if results else 0), ""]
        for name, score in results:
            s = score.summary()
            mark = "  <<" if name == best and len(results) > 1 else ""
            lines.append(f"{name}{mark}")
            lines.append(tr("found {hits} of {objects}, {missed} missed, {false_alarms} false alarms",
                            hits=s["hits"], objects=s["objects"], missed=s["missed"],
                            false_alarms=s["false_alarms"]))
            lines.append(f"precision {s['precision']}  recall {s['recall']}  F1 {s['f1']}  "
                         f"{tr('overlap')} {s['mean_overlap']}")
            if s["wrong_class"]:
                lines.append(tr("{n} objects found in the right place but with the wrong class",
                                n=s["wrong_class"]))
            lines.append("")
        self.card.setPlainText("\n".join(lines))
        self.status.setText(tr("Test finished."))

    def _test_failed(self, error: Exception) -> None:
        self.bar.setVisible(False)
        self.btn_test.setEnabled(True)
        self.status.setText(tr("Error: {msg}", msg=tr_error(error)))
