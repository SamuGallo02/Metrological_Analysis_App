"""Dataset di training presenti sul server (area `datasets`). Funzioni senza interfaccia grafica."""
from __future__ import annotations

from typing import Any, Dict, List

DATASETS_AREA = "datasets"
DATA_FILES = ("data.yaml", "data.yml")          # il file che YOLO vuole per sapere dove sono immagini e classi


def list_server_datasets(client: Any) -> List[Dict[str, Any]]:
    """Le cartelle dell'area dei dataset, in ordine alfabetico: {"name", "valid"}.

    "valid" vuol dire che dentro c'è un data.yaml (o data.yml): senza, YOLO non può usarla."""
    found = []
    for e in client.list(DATASETS_AREA, ""):
        if e["type"] != "dir":
            continue                                  # i file sciolti nell'area non sono dataset
        inside = {x["name"] for x in client.list(DATASETS_AREA, e["name"]) if x["type"] == "file"}
        found.append({"name": e["name"], "valid": any(f in inside for f in DATA_FILES)})
    return sorted(found, key=lambda d: d["name"].lower())

def group_datasets_by_species(items: list[dict]) -> list[tuple[str, list[dict]]]:
    """Raggruppa gli elementi del catalogo dei dataset per specie (le classi del data.yaml).
    Un dataset con più specie compare sotto ognuna; quelli senza specie dichiarata vanno in coda, sotto ''."""
    groups: dict[str, list[dict]] = {}
    for item in items:
        for species in item.get("classes") or [""]:
            groups.setdefault(species, []).append(item)
    for members in groups.values():
        members.sort(key=lambda i: (i["date"], i["path"]))
    return sorted(groups.items(), key=lambda g: (g[0] == "", g[0].lower()))