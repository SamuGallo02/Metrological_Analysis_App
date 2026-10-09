"""Choice of PyTorch builds and requirements based on OS and hardware."""

from __future__ import annotations

from typing import List, Optional, Tuple

from .sysinfo import OS_MACOS, SystemInfo

PYTORCH_INDEX = "https://download.pytorch.org/whl/"

# (minimum driver CUDA version, PyTorch index tag), from the most recent
_CUDA_BUILDS = [((12, 6), "cu126"), ((12, 4), "cu124"), ((12, 1), "cu121"), ((11, 8), "cu118")]

# Indicative download estimate, only to inform the user
SIZE_HINT = {"cpu": "circa 0,3 GB", "default": "circa 0,1 GB", "cuda": "circa 2,5-3,5 GB"}


class TorchChoice:
    def __init__(self, label: str, index_url: Optional[str]):
        self.label = label          # "cpu", "default", "cu124"...
        self.index_url = index_url  # None => PyPI

    def __repr__(self) -> str:
        return f"TorchChoice({self.label})"


def core_torch(info: SystemInfo) -> TorchChoice:
    """Build for normal use: never CUDA (multi-GB) automatically."""
    if info.os_name == OS_MACOS:
        return TorchChoice("default", None)  # on PyPI already with MPS
    return TorchChoice("cpu", PYTORCH_INDEX + "cpu")


def training_torch_candidates(info: SystemInfo) -> List[TorchChoice]:
    """CUDA builds compatible with the driver, from the most recent; empty if not needed/no GPU."""
    if not info.nvidia or info.os_name == OS_MACOS:
        return []
    cuda = info.driver_cuda or (12, 1)
    return [TorchChoice(tag, PYTORCH_INDEX + tag) for need, tag in _CUDA_BUILDS if cuda >= need]


def training_needed(info: SystemInfo) -> Tuple[bool, str]:
    """(is anything needed?, explanation for the user)."""
    if info.os_name == OS_MACOS:
        msg = "Apple GPU (MPS) gia' inclusa: nessun componente aggiuntivo necessario."
        return False, msg
    if not info.nvidia:
        return False, "Nessuna GPU NVIDIA rilevata: il training usera' la CPU, nulla da installare."
    if not training_torch_candidates(info):
        return False, "Il driver NVIDIA e' troppo vecchio per le build CUDA di PyTorch: aggiornalo."
    return True, ""
