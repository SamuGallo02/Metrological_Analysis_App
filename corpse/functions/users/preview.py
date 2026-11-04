"""Anteprima di un invio in attesa: quali immagini mostrare (senza interfaccia grafica)."""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Dict

from common.remote_tree import walk_remote

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
PREVIEW_LIMIT = 60


def list_preview(client: Any, area: str, rel: str, limit: int = PREVIEW_LIMIT) -> Dict[str, Any]:
    """Le prime `limit` immagini sotto `rel`, quante sono in tutto e quante restano fuori."""
    images = sorted(path for path, _size in walk_remote(client, area, rel)
                    if PurePosixPath(path).suffix.lower() in IMAGE_SUFFIXES)
    return {"images": images[:limit], "total": len(images), "more": max(0, len(images) - limit)}