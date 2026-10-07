"""
Modulo per la Gestione delle Classi di Oggetto Analizzabili
=============================================================
Mantiene un elenco persistente (file JSON) delle categorie di oggetto
selezionabili nella GUI per filtrare i rilevamenti YOLO (es. "persone",
"veicoli", "animali"...). L'elenco e' modificabile a runtime tramite
add_class()/remove_class() ed e' salvato su disco tra una sessione e l'altra.

Nota: il nome della classe deve corrispondere (case-insensitive) all'etichetta
restituita dal modello YOLO in uso (predictions.names), altrimenti il filtro
non trovera' corrispondenze. Se il modello e' in inglese (es. "person", "car"),
inserisci l'etichetta cosi' come il modello la restituisce.

Autore: Samuele Gallo
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

CLASSES_FILE = Path("object_classes.json")

# Valore speciale che indica "nessun filtro, mostra tutti gli oggetti rilevati"
ALL_OBJECTS = "Tutti gli oggetti"


def load_classes(path: Path = CLASSES_FILE) -> List[str]:
    """Carica l'elenco delle classi salvate. Ritorna lista vuota se il file non esiste o e' corrotto."""
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [str(x) for x in data]
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_classes(classes: List[str], path: Path = CLASSES_FILE) -> None:
    """Salva l'elenco delle classi su file, in ordine e senza duplicati."""
    unique_sorted = sorted(dict.fromkeys(c.strip() for c in classes if c.strip()))
    with path.open("w", encoding="utf-8") as f:
        json.dump(unique_sorted, f, ensure_ascii=False, indent=2)


def add_class(name: str, path: Path = CLASSES_FILE) -> List[str]:
    """Aggiunge una nuova classe (se non gia' presente, case-insensitive) e salva. Ritorna l'elenco aggiornato."""
    name = name.strip()
    classes = load_classes(path)
    if name and name.lower() not in (c.lower() for c in classes):
        classes.append(name)
        save_classes(classes, path)
    return load_classes(path)


def remove_class(name: str, path: Path = CLASSES_FILE) -> List[str]:
    """Rimuove una classe (case-insensitive) e salva. Ritorna l'elenco aggiornato."""
    classes = [c for c in load_classes(path) if c.lower() != name.strip().lower()]
    save_classes(classes, path)
    return classes