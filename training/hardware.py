"""
Rilevamento dell'hardware e della connessione, usato dalla pagina di Training.
Funzioni pure (nessuna dipendenza dall'interfaccia grafica): si possono
provare da sole, senza aprire alcuna finestra.

Autore: Samuele Gallo
"""

from __future__ import annotations


def check_internet_connection() -> bool:
    """Verifica rapida della presenza di una connessione internet attiva."""
    import socket
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except OSError:
        return False


def get_hardware_info() -> tuple[str, str]:
    """Rileva l'hardware disponibile per l'addestramento YOLO (GPU PyTorch/CUDA, MPS o CPU).
    Ritorna (codice device per Ultralytics, descrizione leggibile)."""
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
