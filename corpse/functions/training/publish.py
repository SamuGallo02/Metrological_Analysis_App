"""Pubblicazione di un modello allenato sul server: modello e metadati in models/<Genere specie>/.
Funzioni senza interfaccia grafica: `client` è l'ApiClient della sessione."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from common.errors import AppError
from common.params import SPECIES_EXAMPLE, SPECIES_RE
from common.model_metadata import read_metadata, write_metadata

MODELS_AREA = "models"

Progress = Optional[Callable[[int, int], None]]      # (byte_fatti, byte_totali)
Cancel = Optional[Callable[[], bool]]


def publish_model(client: Any, model_path: Path, species: str, progress: Progress = None,
                  cancel: Cancel = None) -> Dict[str, Any]:
    """Carica il modello (e i suoi metadati, se ci sono) in models/<species>/.

    Restituisce {"remote", "pending", "metadata"}: `pending` è vero se il modello aspetta l'approvazione di un
    amministratore (utente normale), falso se è già pubblico (amministratore)."""
    species = species.strip()
    if not re.fullmatch(SPECIES_RE, species):
        raise AppError("Enter the scientific name as 'Genus species', for example {example}.", 422,
                       example=SPECIES_EXAMPLE)                      # controllato PRIMA di caricare qualsiasi cosa

    model = Path(model_path)
    meta = read_metadata(model)
    meta_path: Optional[Path] = None
    if meta is not None:
        meta["species"] = species                                     # la specie scelta entra nei metadati
        meta_path = write_metadata(model, meta)                       # e si rifanno nome, dimensione e impronta

    files = [model] + ([meta_path] if meta_path else [])             # prima il modello: se i metadati falliscono resta approvabile
    total = sum(f.stat().st_size for f in files)
    done = 0
    for f in files:
        base = done
        client.upload(MODELS_AREA, f"{species}/{f.name}", f,
                            (lambda d, _t, base=base: progress(base + d, total)) if progress else None, cancel)
        done += f.stat().st_size
        if progress:
            progress(done, total)
    sent = client.submit_model(species, model.name)                  # il server decide: admin → pubblico, utente → in attesa
    return {"remote": f"{species}/{model.name}", "pending": bool(sent.get("pending")), "metadata": meta_path is not None}