"""Detection of operating system and hardware (standard library only)."""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional, Tuple

OS_WINDOWS, OS_MACOS, OS_LINUX = "windows", "macos", "linux"

_NVSMI_FALLBACKS = (r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",)


@dataclass
class SystemInfo:
    os_name: str
    arch: str
    python: Tuple[int, int, int]
    apple_silicon: bool = False
    nvidia: bool = False
    gpu_name: str = ""
    driver_cuda: Optional[Tuple[int, int]] = None  # maximum CUDA version supported by the driver

    def describe(self) -> str:
        py = ".".join(map(str, self.python))
        if self.nvidia:
            cuda = f"{self.driver_cuda[0]}.{self.driver_cuda[1]}" if self.driver_cuda else "?"
            gpu = f"GPU NVIDIA {self.gpu_name} (driver CUDA {cuda})"
        elif self.apple_silicon:
            gpu = "Apple Silicon (accelerazione MPS integrata)"
        else:
            gpu = "nessuna GPU NVIDIA"
        return f"{self.os_name} {self.arch}, Python {py}, {gpu}"


def detect_os() -> str:
    if sys.platform.startswith("win"):
        return OS_WINDOWS
    if sys.platform == "darwin":
        return OS_MACOS
    return OS_LINUX


def _find_nvidia_smi() -> Optional[str]:
    path = shutil.which("nvidia-smi")
    if path:
        return path
    import os
    for cand in _NVSMI_FALLBACKS:
        if os.path.exists(cand):
            return cand
    return None


def _query_nvidia() -> Tuple[bool, str, Optional[Tuple[int, int]]]:
    smi = _find_nvidia_smi()
    if not smi:
        return False, "", None
    try:
        out = subprocess.run([smi], capture_output=True, text=True, timeout=20)
    except Exception:
        return False, "", None
    if out.returncode != 0:
        return False, "", None

    cuda = None
    m = re.search(r"CUDA Version:\s*(\d+)\.(\d+)", out.stdout)
    if m:
        cuda = (int(m.group(1)), int(m.group(2)))

    name = ""
    try:
        q = subprocess.run([smi, "--query-gpu=name", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=20)
        if q.returncode == 0 and q.stdout.strip():
            name = q.stdout.strip().splitlines()[0].strip()
    except Exception:
        pass
    return True, name, cuda


def detect_system() -> SystemInfo:
    os_name = detect_os()
    machine = platform.machine().lower()
    nvidia, gpu_name, cuda = False, "", None
    if os_name != OS_MACOS:  # recent Macs have no NVIDIA drivers
        nvidia, gpu_name, cuda = _query_nvidia()
    return SystemInfo(
        os_name=os_name,
        arch=machine,
        python=tuple(sys.version_info[:3]),
        apple_silicon=(os_name == OS_MACOS and machine in ("arm64", "aarch64")),
        nvidia=nvidia,
        gpu_name=gpu_name,
        driver_cuda=cuda,
    )
