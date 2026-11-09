"""Folder selection for the analysis pages, backed by the media library: folders are registered where they are,
never copied (see corpse.functions.library)."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from corpse.functions.analysis.library import default_library

MISSING = " (non trovata)"


def add_folder(page: QWidget, kind: str, title: str, validate: Optional[Callable[[Path], Optional[str]]] = None) -> None:
    """Asks for a folder and registers it in place. `validate(path)` returns an error text or None."""
    start = default_library().sources(kind)
    initial = str(start[-1].path.parent) if start else str(Path.home())
    chosen = QFileDialog.getExistingDirectory(page, title, initial)
    if not chosen:
        return
    folder = Path(chosen)
    error = validate(folder) if validate else None
    if error:
        QMessageBox.critical(page, "Cartella non valida", error)
        return
    try:
        src = default_library().add_source(kind, folder)
    except (OSError, ValueError) as exc:
        QMessageBox.critical(page, "Errore", f"Impossibile aggiungere la cartella:\n{exc}")
        return
    refresh(page, kind, select=src.name)


def remove_selected(page: QWidget, kind: str) -> None:
    """Removes the selected folder from the list. The files on disk are not touched."""
    name = page.folder_combo.currentData()
    src = default_library().source(kind, name) if name else None
    if src is None:
        return
    ok = QMessageBox.question(page, "Rimuovi dall'elenco",
                              f"Togliere '{src.name}' dall'elenco?\nI file in {src.path} non vengono toccati.",
                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    if ok == QMessageBox.StandardButton.Yes:
        default_library().remove_source(src.id)
        refresh(page, kind)


def refresh(page: QWidget, kind: str, select: Optional[str] = None, empty_text: str = "Nessuna cartella: usa 'Aggiungi cartella...'") -> None:
    """Fills page.folder_combo from the library and sets page.selected_folder (None if nothing usable)."""
    combo = page.folder_combo
    current = select or combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    sources = default_library().sources(kind)
    if not sources:
        combo.addItem(empty_text, None)
        combo.setEnabled(False)
    else:
        combo.setEnabled(True)
        for s in sources:
            combo.addItem(s.name + ("" if s.exists else MISSING), s.name)
        index = combo.findData(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
    combo.blockSignals(False)
    on_selected(page, kind)


def on_selected(page: QWidget, kind: str) -> None:
    name = page.folder_combo.currentData()
    src = default_library().source(kind, name) if name else None
    page.selected_folder = str(src.path) if src is not None and src.exists else None
    page._update_run_button_state()
