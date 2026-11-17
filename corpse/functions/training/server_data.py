"""Training datasets that live on the server (area `datasets`). Functions without a graphical interface.

Autore: Samuele Gallo
"""
from __future__ import annotations

from typing import Any, Dict, List

DATASETS_AREA = "datasets"
DATA_FILES = ("data.yaml", "data.yml")          # il file che YOLO vuole per sapere dove sono immagini e classi


def list_server_datasets(client: Any) -> List[Dict[str, Any]]:
    """The folders of the dataset area, in alphabetical order: {"name", "valid"}.

    "valid" means it holds a data.yaml (or data.yml): without one, YOLO cannot use it."""
    found = []
    for e in client.list(DATASETS_AREA, ""):
        if e["type"] != "dir":
            continue                                  # i file sciolti nell'area non sono dataset
        inside = {x["name"] for x in client.list(DATASETS_AREA, e["name"]) if x["type"] == "file"}
        found.append({"name": e["name"], "valid": any(f in inside for f in DATA_FILES)})
    return sorted(found, key=lambda d: d["name"].lower())

def group_datasets_by_species(items: list[dict]) -> list[tuple[str, list[dict]]]:
    """Raggruppa gli elementi del catalogo dei dataset per specie (le classi del data.yaml).
    A dataset of several species appears under each of them; those with no declared species go last, under ''."""
    groups: dict[str, list[dict]] = {}
    for item in items:
        for species in item.get("classes") or [""]:
            groups.setdefault(species, []).append(item)
    for members in groups.values():
        members.sort(key=lambda i: (i["date"], i["path"]))
    return sorted(groups.items(), key=lambda g: (g[0] == "", g[0].lower()))