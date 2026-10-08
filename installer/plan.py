"""Scelta delle build di PyTorch e dei requisiti in base a OS e hardware."""

from __future__ import annotations

from typing import List, Optional, Tuple

from .sysinfo import OS_MACOS, SystemInfo

PYTORCH_INDEX = "https://download.pytorch.org/whl/"

# (versione CUDA minima del driver, tag dell'indice PyTorch), dalla piu' recente
_CUDA_BUILDS = [((12, 6), "cu126"), ((12, 4), "cu124"), ((12, 1), "cu121"), ((11, 8), "cu118")]

# Stima indicativa del download, solo per informare l'utente
SIZE_HINT = {"cpu": "circa 0,3 GB", "default": "circa 0,1 GB", "cuda": "circa 2,5-3,5 GB"}


class TorchChoice:
    def __init__(self, label: str, index_url: Optional[str]):
        self.label = label          # "cpu", "default", "cu124"...
        self.index_url = index_url  # None => PyPI

    def __repr__(self) -> str:
        return f"TorchChoice({self.label})"


def core_torch(info: SystemInfo) -> TorchChoice:
    """Build per l'uso normale: mai CUDA (multi-GB) in automatico."""
    if info.os_name == OS_MACOS:
        return TorchChoice("default", None)  # su PyPI gia' con MPS
    return TorchChoice("cpu", PYTORCH_INDEX + "cpu")


def training_torch_candidates(info: SystemInfo) -> List[TorchChoice]:
    """Build CUDA compatibili col driver, dalla piu' recente; vuoto se non serve/non c'e' GPU."""
    if not info.nvidia or info.os_name == OS_MACOS:
        return []
    cuda = info.driver_cuda or (12, 1)
    return [TorchChoice(tag, PYTORCH_INDEX + tag) for need, tag in _CUDA_BUILDS if cuda >= need]


def training_needed(info: SystemInfo) -> Tuple[bool, str]:
    """(serve qualcosa?, spiegazione per l'utente)."""
    if info.os_name == OS_MACOS:
        msg = "Apple GPU (MPS) gia' inclusa: nessun componente aggiuntivo necessario."
        return False, msg
    if not info.nvidia:
        return False, "Nessuna GPU NVIDIA rilevata: il training usera' la CPU, nulla da installare."
    if not training_torch_candidates(info):
        return False, "Il driver NVIDIA e' troppo vecchio per le build CUDA di PyTorch: aggiornalo."
    return True, ""
