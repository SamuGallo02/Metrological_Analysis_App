"""
Hardware and connection detection, used by the Training page.
Pure functions (no dependency on the graphical interface): they can be
tested on their own, without opening any window.

Autore: Samuele Gallo
"""

from __future__ import annotations


def check_internet_connection() -> bool:
    """Quick check for an active internet connection."""
    import socket
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except OSError:
        return False


def get_hardware_info() -> tuple[str, str]:
    """Detects the hardware available for YOLO training (PyTorch GPU/CUDA, MPS or CPU).
    Returns (device code for Ultralytics, human-readable description)."""
    try:
        import torch
        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            return "0", f"GPU CUDA ({device_name} - {vram_gb:.1f} GB VRAM)"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps", "Apple Silicon GPU (MPS)"
    except ImportError:
        pass
    return "cpu", "CPU di sistema (Non ottimizzata per training intensivi)"
