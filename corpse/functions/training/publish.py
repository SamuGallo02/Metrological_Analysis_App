"""Publishing a trained model on the server: the model and its metadata go to models/<Genus species>/.

The file is named after the species it recognises - "Pinna_nobilis_yolo11l-seg.pt" - so a model downloaded from
the server says by itself which animal it knows and which network it was built on. No graphical interface here:
`client` is the ApiClient of the session.

Autore: Samuele Gallo
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from common.errors import AppError
from common.params import SPECIES_EXAMPLE, SPECIES_RE
from common.model_metadata import free_name, model_filename, read_metadata, write_metadata

MODELS_AREA = "models"

Progress = Optional[Callable[[int, int], None]]      # (byte_fatti, byte_totali)
Cancel = Optional[Callable[[], bool]]


def publish_model(client: Any, model_path: Path, species: str, progress: Progress = None,
                  cancel: Cancel = None, group: str = "") -> Dict[str, Any]:
    """Uploads the model (and its metadata, if any) to models/<species>/.

    Returns {"remote", "pending", "metadata", "name"}: `pending` is true when the model waits for the approval
    of an administrator (ordinary user), false when it is already public (administrator)."""
    species = species.strip()
    if not re.fullmatch(SPECIES_RE, species):
        raise AppError("Enter the scientific name as 'Genus species', for example {example}.", 422,
                       example=SPECIES_EXAMPLE)                      # controllato PRIMA di caricare qualsiasi cosa

    model = Path(model_path)
    meta = read_metadata(model)
    model = _named_after(model, species, meta)                        # the file takes the name of its species
    meta_path: Optional[Path] = None
    if meta is not None:
        meta["species"] = species                                     # the chosen species goes into the metadata
        meta_path = write_metadata(model, meta)                       # and name, size and fingerprint are redone

    files = [model] + ([meta_path] if meta_path else [])             # the model first: if the metadata fails, it can still be approved
    total = sum(f.stat().st_size for f in files)
    done = 0
    for f in files:
        base = done
        client.upload(MODELS_AREA, f"{species}/{f.name}", f,
                            (lambda d, _t, base=base: progress(base + d, total)) if progress else None, cancel)
        done += f.stat().st_size
        if progress:
            progress(done, total)
    sent = client.submit_model(species, model.name, group)           # the server decides: admin -> public, user -> waiting
    return {"remote": f"{species}/{model.name}", "pending": bool(sent.get("pending")),
            "metadata": meta_path is not None, "name": model.name}


def _named_after(model: Path, species: str, meta: Optional[Dict[str, Any]]) -> Path:
    """Renames the model (and the metadata beside it) after the species it recognises, if it is not named so
    already. The file stays where it is: only its name changes, here and on the server."""
    wanted = model_filename(species, (meta or {}).get("base_model") or model.name)
    if model.name == wanted:
        return model
    target = free_name(model.parent, wanted)
    try:
        old_meta = model.with_suffix(".json")
        model = Path(model.replace(target))
        if old_meta.is_file():
            old_meta.replace(model.with_suffix(".json"))
    except OSError:
        return Path(model)                                           # read-only folder: the name it has will do
    return model