"""Scaricamento di una cartella intera dal server (senza interfaccia grafica).

Riceve il client (ApiClient) come argomento: così sta in `common`, senza importare nessuna sezione,
e lo possono usare sia il browser delle cartelle sia il Training.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Callable, List, Optional, Tuple

Progress = Optional[Callable[[int, int], None]]      # (byte_fatti, byte_totali)
Cancel = Optional[Callable[[], bool]]


def walk_remote(client: Any, area: str, rel: str) -> List[Tuple[str, int]]:
    """Elenco ricorsivo (percorso, dimensione) dei file sotto `rel`."""
    out: List[Tuple[str, int]] = []
    for e in client.list(area, rel):
        child = f"{rel}/{e['name']}" if rel else e["name"]
        if e["type"] == "dir":
            out.extend(walk_remote(client, area, child))
        else:
            out.append((child, e["size"]))
    return out


def download_tree(client: Any, area: str, remote: str, dest: Path, progress: Progress = None,
                  cancel: Cancel = None) -> int:
    """Scarica la cartella `remote` dentro `dest`; restituisce il numero di file della cartella.

    I file già presenti non si scaricano di nuovo: un download interrotto riprende da dove era."""
    files = walk_remote(client, area, remote)
    total = sum(size for _rel, size in files)
    done = 0
    for rel, size in files:
        local = Path(dest) / PurePosixPath(rel).relative_to(remote)
        if not local.exists():
            base = done
            client.download(area, rel, local,
                            (lambda d, _t, base=base: progress(base + d, total)) if progress else None, cancel)
        done += size
        if progress:
            progress(done, total)
    return len(files)