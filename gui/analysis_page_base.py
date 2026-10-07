"""
Classe base condivisa dalle quattro pagine "di analisi" dell'applicativo
(Analisi Stereo, Analisi Foto, Analisi Video, Analisi Video Stereo).

Le quattro pagine condividono la STESSA interfaccia (lista + anteprima +
tabelle + filtri classe/modello + esportazione CSV): tenerla scritta una
sola volta qui, invece che copiata quattro volte, e' l'unico modo per
garantire che restino davvero identiche nel tempo, come richiesto — le
uniche differenze reali sono: anteprima singola o doppia camera, presenza
o meno delle colonne di misura/calibrazione, e come si sceglie la sorgente
dei dati (cartella con sottocartelle rx/lx, cartella di foto singole, o un
file video), che ogni sottoclasse configura nel proprio __init__.

Autore: Samuele Gallo
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

import cv2
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from core.analysis import PairResult, StereoConfig, list_model_classes
from core.calibration import load_calibration, save_calibration
from core.object_classes import ALL_OBJECTS, add_class, load_classes, remove_class
from core.reporting import compute_summary, detections_to_dataframe, export_csv
from gui.common_widgets import ClickableImageLabel, build_top_bar, open_zoom_dialog, render_image_to_label

MODELS_DIR = Path("models")


def scan_models(models_dir: Path = MODELS_DIR) -> List[str]:
    if not models_dir.is_dir():
        return []
    return sorted(f.name for f in models_dir.iterdir() if f.suffix.lower() == ".pt")


class AnalysisPageBase(QWidget):
    """
    Scheletro comune a tutte le pagine di analisi. Una sottoclasse DEVE:
      - passare i parametri di configurazione al costruttore (vedi __init__);
      - implementare _resolve_source(), che ritorna cio' che _create_worker
        si aspetta come sorgente dati (path di una cartella, o di un file,
        o una tupla di due path) sollevando un'eccezione con un messaggio
        chiaro se la selezione corrente non e' valida per questa pagina;
      - implementare _create_worker(model_path, target_label, stereo_config,
        source), che ritorna il QThread (gia' pronto, non ancora avviato)
        specifico di quella modalita'.
    Il worker, qualunque sia, deve emettere gli stessi segnali di
    AnalysisWorker: progress(int,int), pair_done(object,int), finished_all(),
    error(str) — e' l'unico contratto richiesto per riusare tutta la parte
    di interfaccia scritta qui.
    """

    def __init__(
            self,
            on_home: Callable[[], None],
            page_title: str,
            dual_preview: bool,
            show_measurements: bool,
            parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.on_home = on_home
        self.page_title = page_title
        self.dual_preview = dual_preview
        self.show_measurements = show_measurements

        self.results: List[PairResult] = []
        self.user_counts: Dict[int, int] = {}
        self.class_user_counts: Dict[str, int] = {}
        self.worker = None
        self.class_checkboxes: Dict[str, QCheckBox] = {}

        self._current_left_image = None
        self._current_right_image = None

        self._build_ui()

    # ------------------------------------------------------------ da implementare nelle sottoclassi
    def _resolve_source(self):
        """Ritorna la sorgente dati corrente, sollevando un'eccezione chiara se non valida."""
        raise NotImplementedError

    def _create_worker(self, model_path: str, target_label, stereo_config: Optional[StereoConfig], source):
        """Costruisce (senza avviare) il QThread di analisi per questa modalita'."""
        raise NotImplementedError

    def _build_source_selector_ui(self, layout: QVBoxLayout) -> None:
        """La sottoclasse aggiunge qui i controlli per scegliere la sorgente (cartella o file)."""
        raise NotImplementedError

    # ------------------------------------------------------------------------------ costruzione UI
    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)

        root_layout.addLayout(build_top_bar(self, self.on_home))
        root_layout.addWidget(QLabel(f"<h2>{self.page_title}</h2>"))

        LABEL_WIDTH = 160
        self._label_width = LABEL_WIDTH

        # --- selettore sorgente dati (diverso per ogni pagina, vedi sottoclassi) ---
        self._build_source_selector_ui(root_layout)

        # --- barra modello YOLO (condivisa) ---
        model_bar = QHBoxLayout()
        lbl_model = QLabel("Modello YOLO:")
        lbl_model.setFixedWidth(LABEL_WIDTH)
        model_bar.addWidget(lbl_model)

        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(220)
        model_bar.addWidget(self.model_combo, stretch=1)

        btn_add_model = QPushButton("Aggiungi modello...")
        btn_add_model.clicked.connect(self._add_model)
        model_bar.addWidget(btn_add_model)

        btn_refresh_models = QPushButton("Aggiorna elenco")
        btn_refresh_models.clicked.connect(self._refresh_models)
        model_bar.addWidget(btn_refresh_models)

        btn_show_classes = QPushButton("Vedi classi del modello")
        btn_show_classes.clicked.connect(self._show_model_classes)
        model_bar.addWidget(btn_show_classes)
        root_layout.addLayout(model_bar)

        # --- barra classe oggetto (condivisa) ---
        class_bar = QHBoxLayout()
        lbl_class = QLabel("Oggetti da analizzare:")
        lbl_class.setFixedWidth(LABEL_WIDTH)
        class_bar.addWidget(lbl_class)

        self.btn_class_select = QComboBox()
        self.btn_class_select.setMinimumWidth(220)
        self.class_menu = QMenu(self)
        self.btn_class_select.showPopup = lambda: self.class_menu.exec(
            self.btn_class_select.mapToGlobal(self.btn_class_select.rect().bottomLeft())
        )
        class_bar.addWidget(self.btn_class_select, stretch=1)

        btn_add_class = QPushButton("Aggiungi oggetto...")
        btn_add_class.clicked.connect(self._add_object_class)
        class_bar.addWidget(btn_add_class)

        btn_remove_class = QPushButton("Rimuovi oggetto")
        btn_remove_class.clicked.connect(self._remove_object_class)
        class_bar.addWidget(btn_remove_class)
        root_layout.addLayout(class_bar)

        # --- barra pulsanti avvia / esporta (niente piu' pulsante training qui) ---
        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(0, 5, 0, 5)

        self.btn_run = QPushButton("AVVIA ANALISI")
        self.btn_run.setMinimumHeight(40)
        self.btn_run.setFixedWidth(220)
        self.btn_run.setStyleSheet("""
            QPushButton { background-color: #2e7d32; color: white; font-weight: bold; font-size: 13px; border-radius: 5px; }
            QPushButton:hover { background-color: #388e3c; }
            QPushButton:disabled { background-color: #444444; color: #888888; }
        """)
        self.btn_run.setEnabled(False)
        self.btn_run.clicked.connect(self._run_analysis)

        self.btn_export = QPushButton("ESPORTA CSV")
        self.btn_export.setMinimumHeight(40)
        self.btn_export.setFixedWidth(160)
        self.btn_export.setStyleSheet("""
            QPushButton { background-color: #1565c0; color: white; font-weight: bold; font-size: 13px; border-radius: 5px; }
            QPushButton:hover { background-color: #1976d2; }
            QPushButton:disabled { background-color: #444444; color: #888888; }
        """)
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export_csv)

        action_bar.addWidget(self.btn_run)
        action_bar.addWidget(self.btn_export)
        action_bar.addStretch(1)
        root_layout.addLayout(action_bar)

        # --- toggle vista variazioni (condiviso) ---
        toggle_bar = QHBoxLayout()
        self.btn_toggle_changes = QPushButton("Mostra solo variazioni")
        self.btn_toggle_changes.setCheckable(True)
        self.btn_toggle_changes.setEnabled(False)
        self.btn_toggle_changes.toggled.connect(self._on_toggle_changes_view)
        toggle_bar.addWidget(self.btn_toggle_changes)
        toggle_bar.addStretch(1)
        root_layout.addLayout(toggle_bar)

        self._refresh_object_classes()
        self._refresh_models()

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        root_layout.addWidget(self.progress_bar)

        # --- pannello centrale: lista | anteprima(e) | tabelle ---
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        self.pair_list = QListWidget()
        self.pair_list.setMinimumWidth(140)
        self.pair_list.setMaximumWidth(500)
        self.pair_list.currentRowChanged.connect(self._show_pair_preview)
        self.splitter.addWidget(self.pair_list)

        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(5, 5, 5, 5)
        preview_images_layout = QHBoxLayout()
        preview_images_layout.setSpacing(10)

        left_col = QVBoxLayout()
        left_title = "Camera Sinistra (lx) + Overlay Rilevamenti" if self.dual_preview else "Overlay Rilevamenti"
        lbl_left_title = QLabel(left_title)
        lbl_left_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_col.addWidget(lbl_left_title)

        self.preview_left_label = ClickableImageLabel("Nessun elemento selezionato")
        self.preview_left_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_left_label.setStyleSheet("background-color: #181818; color: #888888; border-radius: 4px;")
        self.preview_left_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_left_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview_left_label.clicked.connect(lambda: open_zoom_dialog(self, self._current_left_image))
        left_col.addWidget(self.preview_left_label)
        preview_images_layout.addLayout(left_col, stretch=1)

        self.preview_right_label = None
        if self.dual_preview:
            right_col = QVBoxLayout()
            lbl_right_title = QLabel("Camera Destra (rx)")
            lbl_right_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            right_col.addWidget(lbl_right_title)

            self.preview_right_label = ClickableImageLabel("Nessun elemento selezionato")
            self.preview_right_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.preview_right_label.setStyleSheet("background-color: #181818; color: #888888; border-radius: 4px;")
            self.preview_right_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.preview_right_label.setCursor(Qt.CursorShape.PointingHandCursor)
            self.preview_right_label.clicked.connect(lambda: open_zoom_dialog(self, self._current_right_image))
            right_col.addWidget(self.preview_right_label)
            preview_images_layout.addLayout(right_col, stretch=1)

        preview_layout.addLayout(preview_images_layout)
        self.splitter.addWidget(preview_container)

        # --- pannello destro: calibrazione (solo se ci sono misure) + tabelle ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        if self.show_measurements:
            right_layout.addWidget(QLabel("Calibrazione Fotocamera Stereo"))
            calib_form = QHBoxLayout()
            saved_config = load_calibration()

            calib_form.addWidget(QLabel("Baseline (mm):"))
            self.spin_baseline = QDoubleSpinBox()
            self.spin_baseline.setRange(1.0, 2000.0)
            self.spin_baseline.setDecimals(1)
            self.spin_baseline.setSingleStep(0.5)
            self.spin_baseline.setValue(saved_config.baseline_mm)
            calib_form.addWidget(self.spin_baseline)

            calib_form.addWidget(QLabel("Focale (px):"))
            self.spin_focal = QDoubleSpinBox()
            self.spin_focal.setRange(1.0, 20000.0)
            self.spin_focal.setDecimals(1)
            self.spin_focal.setSingleStep(10.0)
            self.spin_focal.setValue(saved_config.focal_length_px)
            calib_form.addWidget(self.spin_focal)
            calib_form.addStretch(1)
            right_layout.addLayout(calib_form)

            self.spin_baseline.valueChanged.connect(self._save_calibration_fields)
            self.spin_focal.valueChanged.connect(self._save_calibration_fields)

        right_layout.addWidget(QLabel("Rilevamenti"))
        if self.show_measurements:
            columns = ["Elemento", "N soggetti", "ID Presenti", "Distanza (mm)",
                       "Lunghezza (mm)", "Larghezza (mm)", "Copertura (%)", "Confidenza"]
        else:
            columns = ["Elemento", "N soggetti", "ID Presenti", "Copertura (%)", "Confidenza"]
        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        right_layout.addWidget(self.table)

        right_layout.addWidget(QLabel("Statistiche Aggregate per Singolo ID"))
        if self.show_measurements:
            sum_columns = ["ID", "Classe", "Apparizioni", "Lunghezza Media (mm)", "Larghezza Media (mm)", "Confidenza Media"]
        else:
            sum_columns = ["ID", "Classe", "Apparizioni", "Confidenza Media"]
        self.summary_table = QTableWidget(0, len(sum_columns))
        self.summary_table.setHorizontalHeaderLabels(sum_columns)
        self.summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.summary_table.setMaximumHeight(140)
        right_layout.addWidget(self.summary_table)

        lbl_class_summary = QLabel("Statistiche Aggregate per Classe")
        lbl_class_summary.setStyleSheet("font-weight: bold; margin-top: 5px;")
        right_layout.addWidget(lbl_class_summary)

        if self.show_measurements:
            cls_columns = ["Classe", "N° Soggetti Rilevati", "N° Soggetti Corretto (manuale)", "Lunghezza Media (mm)", "Larghezza Media (mm)"]
        else:
            cls_columns = ["Classe", "N° Soggetti Rilevati", "N° Soggetti Corretto (manuale)"]
        self.class_summary_table = QTableWidget(0, len(cls_columns))
        self.class_summary_table.setHorizontalHeaderLabels(cls_columns)
        self.class_summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.class_summary_table.setMaximumHeight(150)
        right_layout.addWidget(self.class_summary_table)

        self.splitter.addWidget(right_panel)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 3 if self.dual_preview else 2)
        self.splitter.setStretchFactor(2, 2)
        self.splitter.setSizes([180, 650, 450])

        root_layout.addWidget(self.splitter, stretch=1)

        # Ora che ogni widget esiste, ricalcola lo stato reale del pulsante Avvia
        # (durante la costruzione del selettore sorgente, sopra, potrebbe essere
        # stato chiamato troppo presto e quindi ignorato).
        self._update_run_button_state()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "pair_list") and self.pair_list.currentRow() >= 0:
            self._show_pair_preview(self.pair_list.currentRow())

    # ------------------------------------------------------------------------- calibrazione (solo se show_measurements)
    def _current_stereo_config(self) -> Optional[StereoConfig]:
        if not self.show_measurements:
            return None
        return StereoConfig(baseline_mm=self.spin_baseline.value(), focal_length_px=self.spin_focal.value())

    def _save_calibration_fields(self, _value: float = 0.0) -> None:
        cfg = self._current_stereo_config()
        if cfg is not None:
            save_calibration(cfg)

    # ------------------------------------------------------------------------------------------ gestione classi
    def _refresh_object_classes(self) -> None:
        selected_classes = self._get_selected_classes()
        self.class_menu.clear()
        self.class_checkboxes.clear()

        classes = load_classes()

        chk_all = QCheckBox(ALL_OBJECTS)
        chk_all.setStyleSheet("padding: 4px 8px; font-weight: bold;")
        action_all = QWidgetAction(self.class_menu)
        action_all.setDefaultWidget(chk_all)
        self.class_menu.addAction(action_all)
        self.class_checkboxes[ALL_OBJECTS] = chk_all

        if not selected_classes or ALL_OBJECTS in selected_classes:
            chk_all.setChecked(True)
        chk_all.toggled.connect(self._on_all_objects_toggled)

        for cls_name in classes:
            chk = QCheckBox(cls_name)
            chk.setStyleSheet("padding: 4px 8px;")
            if ALL_OBJECTS not in selected_classes and cls_name in selected_classes:
                chk.setChecked(True)
            chk.toggled.connect(self._on_class_checkbox_toggled)

            action = QWidgetAction(self.class_menu)
            action.setDefaultWidget(chk)
            self.class_menu.addAction(action)
            self.class_checkboxes[cls_name] = chk

        self._update_class_button_text()

    def _on_all_objects_toggled(self, checked: bool) -> None:
        if checked:
            for name, chk in self.class_checkboxes.items():
                if name != ALL_OBJECTS:
                    chk.blockSignals(True)
                    chk.setChecked(False)
                    chk.blockSignals(False)
        self._update_class_button_text()

    def _on_class_checkbox_toggled(self, checked: bool) -> None:
        if checked and ALL_OBJECTS in self.class_checkboxes:
            self.class_checkboxes[ALL_OBJECTS].blockSignals(True)
            self.class_checkboxes[ALL_OBJECTS].setChecked(False)
            self.class_checkboxes[ALL_OBJECTS].blockSignals(False)

        if not self._get_selected_classes() and ALL_OBJECTS in self.class_checkboxes:
            self.class_checkboxes[ALL_OBJECTS].blockSignals(True)
            self.class_checkboxes[ALL_OBJECTS].setChecked(True)
            self.class_checkboxes[ALL_OBJECTS].blockSignals(False)

        self._update_class_button_text()

    def _get_selected_classes(self) -> List[str]:
        if not hasattr(self, "class_checkboxes") or not self.class_checkboxes:
            return [ALL_OBJECTS]
        selected = [name for name, chk in self.class_checkboxes.items() if chk.isChecked()]
        return selected if selected else [ALL_OBJECTS]

    def _update_class_button_text(self) -> None:
        selected = self._get_selected_classes()
        if ALL_OBJECTS in selected or not selected:
            text = "Tutti gli oggetti"
        elif len(selected) == 1:
            text = selected[0]
        else:
            text = f"{len(selected)} classi selezionate ({', '.join(selected)})"
        self.btn_class_select.clear()
        self.btn_class_select.addItem(text)

    def _add_object_class(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Aggiungi oggetto",
            "Nome della classe (deve corrispondere all'etichetta usata dal modello YOLO):"
        )
        if not ok or not name.strip():
            return
        add_class(name.strip())
        self._refresh_object_classes()

    def _remove_object_class(self) -> None:
        selected = [name for name in self._get_selected_classes() if name != ALL_OBJECTS]
        if not selected:
            QMessageBox.information(self, "Nessuna selezione", "Seleziona/spunta almeno una classe specifica da rimuovere.")
            return
        reply = QMessageBox.question(
            self, "Conferma rimozione",
            f"Rimuovere le seguenti classi dall'elenco?\n\n{', '.join(selected)}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        for name in selected:
            remove_class(name)
        self._refresh_object_classes()

    # ------------------------------------------------------------------------------------------ gestione modelli
    def _show_model_classes(self) -> None:
        model_name = self.model_combo.currentText()
        if not model_name or not (MODELS_DIR / model_name).is_file():
            QMessageBox.warning(self, "Nessun modello selezionato", "Seleziona prima un modello valido.")
            return
        try:
            classes = list_model_classes(str(MODELS_DIR / model_name))
        except Exception as exc:
            QMessageBox.critical(self, "Errore caricamento modello", f"Impossibile leggere le classi:\n{exc}")
            return
        if not classes:
            QMessageBox.information(self, "Nessuna classe", "Il modello non espone nomi di classe.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Classi del modello — {model_name}")
        dialog.resize(350, 450)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"<b>Etichette rilevabili ({len(classes)} totali):</b>"))
        text_area = QTextEdit()
        text_area.setReadOnly(True)
        text_area.setPlainText("\n".join(f"{i}: {name}" for i, name in enumerate(classes)))
        layout.addWidget(text_area)
        btn_close = QPushButton("Chiudi")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)
        dialog.exec()

    def _add_model(self) -> None:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        source_path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona modello YOLO (.pt)", str(MODELS_DIR.resolve()), "Modelli YOLO (*.pt)"
        )
        if not source_path:
            return
        source = Path(source_path)
        dest = MODELS_DIR / source.name
        if dest.exists():
            reply = QMessageBox.question(
                self, "File esistente", f"Un modello denominato '{source.name}' è già presente. Sovrascrivere?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        try:
            shutil.copy2(source, dest)
        except OSError as exc:
            QMessageBox.critical(self, "Errore di copia", f"Impossibile copiare il file:\n{exc}")
            return
        self._refresh_models()
        self.model_combo.setCurrentText(source.name)

    def _refresh_models(self) -> None:
        current = self.model_combo.currentText()
        self.model_combo.clear()
        models = scan_models()
        if not models:
            self.model_combo.addItem("Nessun modello trovato in models/")
            self.model_combo.setEnabled(False)
        else:
            self.model_combo.setEnabled(True)
            self.model_combo.addItems(models)
            if current in models:
                self.model_combo.setCurrentText(current)
        self._update_run_button_state()

    def _update_run_button_state(self) -> None:
        """Le sottoclassi possono sovrascrivere per aggiungere altre condizioni (es. sorgente selezionata)."""
        if not hasattr(self, "btn_run") or not hasattr(self, "model_combo"):
            return  # chiamata prematura durante la costruzione dell'UI: ignorata, richiamata di nuovo a fine _build_ui
        self.btn_run.setEnabled(self.model_combo.isEnabled())

    # ------------------------------------------------------------------------------------------------ analisi
    def _run_analysis(self) -> None:
        model_name = self.model_combo.currentText()
        if not model_name or not (MODELS_DIR / model_name).is_file():
            QMessageBox.warning(self, "Seleziona modello", "Selezionare un modello YOLO valido.")
            return

        try:
            source = self._resolve_source()
        except Exception as exc:
            QMessageBox.critical(self, "Sorgente non valida", str(exc))
            return

        model_path = str(MODELS_DIR / model_name)
        selected_classes = self._get_selected_classes()
        if ALL_OBJECTS in selected_classes or not selected_classes:
            target_label = None
        elif len(selected_classes) == 1:
            target_label = selected_classes[0]
        else:
            target_label = selected_classes

        self.results.clear()
        self.user_counts.clear()
        self.class_user_counts.clear()
        self.pair_list.clear()
        self.table.setRowCount(0)
        self.summary_table.setRowCount(0)
        self.class_summary_table.setRowCount(0)

        self.btn_toggle_changes.blockSignals(True)
        self.btn_toggle_changes.setChecked(False)
        self.btn_toggle_changes.blockSignals(False)
        self.btn_toggle_changes.setText("Mostra solo variazioni")
        self.btn_toggle_changes.setEnabled(False)

        self.btn_run.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        stereo_config = self._current_stereo_config()
        self.worker = self._create_worker(model_path, target_label, stereo_config, source)
        self.worker.progress.connect(self._on_progress)
        self.worker.pair_done.connect(self._on_pair_done)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_progress(self, current: int, total: int) -> None:
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def _on_pair_done(self, result: PairResult, cumulative_count: int) -> None:
        self.results.append(result)
        idx = len(self.results) - 1
        count = self.user_counts.get(idx, cumulative_count)

        item = QListWidgetItem(f"{result.timestamp} ({count} elementi)")
        item.setData(Qt.ItemDataRole.UserRole, (idx, None))
        self.pair_list.addItem(item)

        current_ids = sorted({det.track_id for det in result.detections if det.track_id is not None})
        ids_str = ", ".join(current_ids) if current_ids else "-"

        coverage_pct = 0.0
        if result.left_image is not None and result.left_image.size > 0:
            frame_area_px = result.left_image.shape[0] * result.left_image.shape[1]
            covered_px = sum(cv2.contourArea(det.contour) for det in result.detections)
            coverage_pct = (covered_px / frame_area_px) * 100.0 if frame_area_px > 0 else 0.0

        for det in result.detections:
            row = self.table.rowCount()
            self.table.insertRow(row)
            col = 0
            self.table.setItem(row, col, QTableWidgetItem(result.timestamp)); col += 1
            self.table.setItem(row, col, QTableWidgetItem(str(count))); col += 1
            self.table.setItem(row, col, QTableWidgetItem(ids_str)); col += 1
            if self.show_measurements:
                self.table.setItem(row, col, QTableWidgetItem(
                    f"{det.contact_distance_mm:.1f}" if det.contact_distance_mm is not None else "-")); col += 1
                self.table.setItem(row, col, QTableWidgetItem(
                    f"{det.length_mm:.1f}" if det.length_mm is not None else "-")); col += 1
                self.table.setItem(row, col, QTableWidgetItem(
                    f"{det.width_mm:.1f}" if det.width_mm is not None else "-")); col += 1
            self.table.setItem(row, col, QTableWidgetItem(f"{coverage_pct:.2f}")); col += 1
            self.table.setItem(row, col, QTableWidgetItem(f"{det.confidence:.2f}"))

    def _on_finished(self) -> None:
        self.progress_bar.setVisible(False)
        self.btn_run.setEnabled(True)
        self.btn_export.setEnabled(bool(self.results))
        self.btn_toggle_changes.setEnabled(bool(self.results))
        self._update_summary()

        if self.pair_list.count() > 0:
            self.pair_list.setCurrentRow(0)

    def _on_error(self, message: str) -> None:
        self.progress_bar.setVisible(False)
        self.btn_run.setEnabled(True)
        QMessageBox.critical(self, "Errore di analisi", message)

    # ------------------------------------------------------------------------------------- vista variazioni
    def _compute_changes_info(self) -> List[dict]:
        changes_info = []
        prev_ids: Set[str] = set()
        for idx, result in enumerate(self.results):
            current_ids = {det.track_id for det in result.detections if det.track_id is not None}
            if idx == 0:
                if current_ids:
                    changes_info.append({"index": idx, "target_ids": current_ids})
            else:
                changed_ids = (current_ids - prev_ids) | (prev_ids - current_ids)
                if changed_ids:
                    changes_info.append({"index": idx, "target_ids": changed_ids})
            prev_ids = current_ids
        return changes_info

    def _build_change_blocks(self) -> List[dict]:
        changes = self._compute_changes_info()
        total = len(self.results)
        blocks = []
        for change in changes:
            c_idx = change["index"]
            start_idx = max(0, c_idx - 2)
            end_idx = min(total - 1, c_idx + 2)
            blocks.append({"var_index": c_idx, "target_ids": change["target_ids"], "range": list(range(start_idx, end_idx + 1))})
        return blocks

    def _rebuild_pair_list_full(self) -> None:
        self.pair_list.clear()
        for idx, result in enumerate(self.results):
            count = self.user_counts.get(idx, len(result.detections))
            item = QListWidgetItem(f"{result.timestamp} ({count} elementi)")
            item.setData(Qt.ItemDataRole.UserRole, (idx, None))
            self.pair_list.addItem(item)

    def _rebuild_pair_list_filtered(self) -> None:
        self.pair_list.clear()
        blocks = self._build_change_blocks()
        if not blocks:
            placeholder = QListWidgetItem("Nessuna variazione rilevata nella sequenza.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.pair_list.addItem(placeholder)
            return
        for block_num, block in enumerate(blocks, start=1):
            var_idx = block["var_index"]
            target_ids = block["target_ids"]
            header = QListWidgetItem(f"── Blocco {block_num} ──")
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            self.pair_list.addItem(header)
            for idx in block["range"]:
                result = self.results[idx]
                count = self.user_counts.get(idx, len(result.detections))
                if idx == var_idx:
                    item_text = f"Variazione {block_num} - {result.timestamp} ({count} elementi)"
                else:
                    item_text = f"{result.timestamp} ({count} elementi)"
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, (idx, target_ids))
                self.pair_list.addItem(item)

    def _on_toggle_changes_view(self, checked: bool) -> None:
        if checked:
            self._rebuild_pair_list_filtered()
            self.btn_toggle_changes.setText("Mostra tutte le coppie")
        else:
            self._rebuild_pair_list_full()
            self.btn_toggle_changes.setText("Mostra solo variazioni")

        for i in range(self.pair_list.count()):
            item = self.pair_list.item(i)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) is not None:
                self.pair_list.setCurrentRow(i)
                break

    # ------------------------------------------------------------------------------------------- statistiche
    def _update_summary(self) -> None:
        try:
            df = detections_to_dataframe(self.results)
            summary_df = compute_summary(df)

            self.summary_table.setRowCount(0)
            if not summary_df.empty:
                for _, row in summary_df.iterrows():
                    r = self.summary_table.rowCount()
                    self.summary_table.insertRow(r)
                    col = 0
                    self.summary_table.setItem(r, col, QTableWidgetItem(str(row["ID"]))); col += 1
                    self.summary_table.setItem(r, col, QTableWidgetItem(str(row["Classe"]))); col += 1
                    self.summary_table.setItem(r, col, QTableWidgetItem(str(row["Apparizioni"]))); col += 1
                    if self.show_measurements:
                        self.summary_table.setItem(r, col, QTableWidgetItem(f"{row['Lunghezza Media (mm)']:.2f}")); col += 1
                        self.summary_table.setItem(r, col, QTableWidgetItem(f"{row['Larghezza Media (mm)']:.2f}")); col += 1
                    self.summary_table.setItem(r, col, QTableWidgetItem(f"{row['Confidenza Media']:.3f}"))

            self.class_summary_table.setRowCount(0)
            if not df.empty:
                grouped = df.groupby("label")
                for cls_name, group in grouped:
                    r = self.class_summary_table.rowCount()
                    self.class_summary_table.insertRow(r)

                    detected_count = len(group["track_id"].unique())
                    corrected_count = self.class_user_counts.get(cls_name, detected_count)

                    item_cls = QTableWidgetItem(str(cls_name))
                    item_cls.setFlags(item_cls.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item_det = QTableWidgetItem(str(detected_count))
                    item_det.setFlags(item_det.flags() & ~Qt.ItemFlag.ItemIsEditable)

                    spin = QSpinBox()
                    spin.setRange(0, 99999)
                    spin.setValue(corrected_count)
                    spin.valueChanged.connect(lambda val, name=cls_name: self._on_class_spinbox_changed(name, val))

                    self.class_summary_table.setItem(r, 0, item_cls)
                    self.class_summary_table.setItem(r, 1, item_det)
                    self.class_summary_table.setCellWidget(r, 2, spin)

                    if self.show_measurements:
                        avg_len = group["length_mm"].mean()
                        avg_wid = group["width_mm"].mean()
                        item_len = QTableWidgetItem(f"{avg_len:.2f}")
                        item_len.setFlags(item_len.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        item_wid = QTableWidgetItem(f"{avg_wid:.2f}")
                        item_wid.setFlags(item_wid.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        self.class_summary_table.setItem(r, 3, item_len)
                        self.class_summary_table.setItem(r, 4, item_wid)

        except Exception as exc:
            QMessageBox.critical(self, "Errore", f"Impossibile aggiornare la tabella riassuntiva:\n{exc}")

    def _on_class_spinbox_changed(self, class_name: str, new_value: int) -> None:
        self.class_user_counts[class_name] = new_value

    # ------------------------------------------------------------------------------------------- anteprima
    def _show_pair_preview(self, row: int) -> None:
        if row < 0 or row >= self.pair_list.count():
            return
        item = self.pair_list.item(row)
        if item is None:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is None:
            return
        idx, target_ids = data
        if idx < 0 or idx >= len(self.results):
            return

        result = self.results[idx]
        from core.analysis import render_overlay
        filtered_overlay = render_overlay(result.left_image, result.detections, filter_ids=target_ids)

        self._current_left_image = filtered_overlay
        self._current_right_image = result.right_image if self.dual_preview else None
        render_image_to_label(self.preview_left_label, filtered_overlay)
        if self.dual_preview and self.preview_right_label is not None:
            render_image_to_label(self.preview_right_label, result.right_image)

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Esporta report CSV", "risultati.csv", "CSV (*.csv)")
        if path:
            try:
                df = detections_to_dataframe(self.results)
                export_csv(df, path)
            except Exception as exc:
                QMessageBox.critical(self, "Errore esportazione", f"Impossibile esportare il CSV:\n{exc}")
                return
            QMessageBox.information(self, "Esportazione completata", f"File salvato con successo in:\n{path}")
