"""Shared display formats."""
from __future__ import annotations

import time
from typing import Optional


def fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def fmt_time(ts: Optional[float]) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "-"


def darker(color: str, factor: float = 0.82) -> str:
    """Solid darker shade of a '#rrggbb' color (hover state: it stays readable with white text on any theme,
    unlike a translucent color, which turns pale over a light window background)."""
    c = color.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(v * factor))) for v in (r, g, b)))
