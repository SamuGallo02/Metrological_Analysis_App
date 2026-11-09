"""Metadati dei modelli allenati: un file .json accanto al modello che racconta come è stato prodotto.

Funzioni senza interfaccia e senza YOLO: si possono provare con dei risultati finti."""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from numbers import Real
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional
import tempfile

from common.errors import AppError
from common.params import SPECIES_RE

SCHEMA = 1                                               # versione del formato del file
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}

# chiavi dei risultati di YOLO -> nome nei metadati (misure sui riquadri, suffisso (B))
_METRIC_KEYS = {"metrics/mAP50(B)": "mAP50", "metrics/mAP50-95(B)": "mAP50_95",
                "metrics/precision(B)": "precision", "metrics/recall(B)": "recall"}


def metrics_from_results(results: Any) -> Dict[str, float]:
    """Legge le misure dai risultati di model.train(); i valori mancanti o strani si lasciano fuori."""
    raw = getattr(results, "results_dict", None)
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, float] = {}
    for key, name in _METRIC_KEYS.items():
        value = raw.get(key)
        if isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value):
            out[name] = float(value)
    return out


def classes_from_data_yaml(yaml_path: Path) -> List[str]:
    """Class names written in a data.yaml file (`names:`), in order of number. Empty list if unreadable."""
    try:
        return classes_from_yaml_text(Path(yaml_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return []


def classes_from_yaml_text(text: str) -> List[str]:
    """Same as `classes_from_data_yaml`, for text already in memory (e.g. a file read from the server)."""
    try:
        import yaml
    except ImportError:                                  # the server uses only the standard library: minimal reader
        return _names_without_yaml(text)
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return []
    names = data.get("names") if isinstance(data, dict) else None
    if isinstance(names, dict):
        return [str(v) for _k, v in sorted(names.items(), key=lambda kv: _order(kv[0]))]
    if isinstance(names, list):
        return [str(v) for v in names]
    return []


def _unquote(text: str) -> str:
    return text.strip().strip("'\"")


def _numbered(pairs: List[str]) -> List[str]:
    """`0: a`, `1: b`... messi in ordine di numero."""
    found = []
    for pair in pairs:
        key, sep, value = pair.partition(":")
        if sep and value.strip():
            found.append((_order(key.strip()), _unquote(value)))
    return [value for _key, value in sorted(found)]


def _names_without_yaml(text: str) -> List[str]:
    """Lettura minima della sezione `names:` quando PyYAML non c'è: lista o dizionario numerato, in riga o a blocchi."""
    lines = text.splitlines()
    for n, line in enumerate(lines):
        if not line.startswith("names:"):
            continue
        rest = line[len("names:"):].split("#")[0].strip()
        if rest.startswith("["):
            return [_unquote(v) for v in rest.strip("[]").split(",") if v.strip()]
        if rest.startswith("{"):
            return _numbered(rest.strip("{}").split(","))
        items: List[str] = []
        for sub in lines[n + 1:]:
            if not sub.strip() or sub.lstrip().startswith("#"):
                continue
            if not sub[:1].isspace() and not sub.startswith("-"):
                break                                    # un'altra sezione del file
            items.append(sub.split("#")[0].strip())
        if items and items[0].startswith("-"):
            return [_unquote(i[1:]) for i in items if i.startswith("-")]
        return _numbered(items)
    return []

def _order(key: Any) -> int:
    try:
        return int(key)
    except (TypeError, ValueError):
        return 10 ** 9


def suggest_species(classes: Iterable[str]) -> Optional[str]:
    """Il nome scientifico, se il dataset ha una sola classe che somiglia a uno: altrimenti None."""
    classes = list(classes)
    if len(classes) != 1:
        return None
    name = re.sub(r"\s+", " ", str(classes[0]).replace("_", " ")).strip().capitalize()
    return name if re.fullmatch(SPECIES_RE, name) else None

def _basename(path: str) -> str:
    """Il nome del file di un percorso, anche se scritto con le barre di Windows."""
    return str(path).replace("\\", "/").rsplit("/", 1)[-1]

def build_metadata(*, base_model: str, dataset_name: str, dataset_source: str, epochs: int, imgsz: int,
                   batch: int, device: str, metrics: Optional[Dict[str, float]] = None,
                   classes: Optional[Iterable[str]] = None, species: Optional[str] = None,
                   trained_by: str = "", dataset_images: Optional[int] = None) -> Dict[str, Any]:
    """Compone i metadati di un training. La specie, se non è indicata, si propone dalle classi."""
    classes = list(classes or [])
    dataset = {"name": dataset_name, "source": dataset_source, "classes": classes}
    if dataset_images is not None:
        dataset["images"] = dataset_images
    return {
        "schema": SCHEMA,
        "species": species if species is not None else suggest_species(classes),
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "trained_by": trained_by,
        "base_model": _basename(base_model),                                        # solo il nome del file      
        "dataset": dataset,
        "parameters": {"epochs": epochs, "imgsz": imgsz, "batch": batch},
        "device": device,
        "metrics": dict(metrics or {}),
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_metadata(model_path: Path, meta: Dict[str, Any]) -> Path:
    """Scrive `<modello>.json` accanto al modello, aggiungendo nome, dimensione e impronta del file."""
    model = Path(model_path)
    data = dict(meta)                                          # l'originale non si modifica
    data["file"] = {"name": model.name, "size": model.stat().st_size, "sha256": _sha256(model)}
    dest = model.with_suffix(".json")
    dest.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return dest


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    """Legge un file JSON che contiene un dizionario; None se manca o non è leggibile."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def read_metadata(model_path: Path) -> Optional[Dict[str, Any]]:
    """Rilegge i metadati di un modello; None se il file manca o non è leggibile."""
    return _load_json(Path(model_path).with_suffix(".json"))

def model_filename(dataset_name: str, base_model: str, when: Optional[datetime] = None) -> str:
    """Il nome del file di un modello appena allenato: <dataset>_<modello base>_<data-ora>.pt.
    Include data e ora, così un nuovo training non sovrascrive il precedente."""
    base = _basename(base_model)
    stem = base[:-3] if base.lower().endswith(".pt") else base
    stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M")
    name = re.sub(r"[^\w.-]+", "_", f"{dataset_name}_{stem}_{stamp}").strip("_")
    return f"{name}.pt"


def count_images(folder: Path) -> int:
    """Quante immagini ci sono in una cartella (e nelle sue sottocartelle): le etichette .txt non contano."""
    folder = Path(folder)
    if not folder.is_dir():
        return 0
    return sum(1 for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)

def fetch_remote_metadata(client: Any, area: str, rel: str) -> Optional[Dict[str, Any]]:
    """Scarica il .json accanto a un modello del server (area/rel) e lo legge.

    None in ogni caso in cui non si può: file mancante, rotto, server che non risponde.
    Chi la usa (il pannello del browser) non deve mai fallire per colpa dei metadati."""
    json_rel = str(PurePosixPath(rel).with_suffix(".json"))
    with tempfile.TemporaryDirectory() as tmp:               # la copia scaricata sparisce a fine lettura
        dest = Path(tmp) / "metadata.json"
        try:
            client.download(area, json_rel, dest)
        except (AppError, OSError):                            # il client vero solleva ApiError, che è un AppError
            return None
        return _load_json(dest)