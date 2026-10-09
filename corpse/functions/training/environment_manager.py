"""
Hardware acceleration status and start of the installation of the
training components. The actual installation lives in installer/ (separate process:
PyTorch cannot be replaced while the app has already loaded it in memory).

Autore: Samuele Gallo
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from common.ambient.installer import plan, state
from common.params import DETACHED_HIDDEN
from common.ambient.installer.sysinfo import detect_system

from common.paths import PROJECT_ROOT  # noqa: E402


def _training_extras_missing() -> bool:
    """True if at least one of the extras in requirements-training.txt is missing (checked without importing them)."""
    import importlib.util
    mods = {"nvidia-ml-py": "pynvml"}
    try:
        for ln in (PROJECT_ROOT / "common" / "ambient" / "requirements" / "requirements-training.txt").read_text(encoding="utf-8").splitlines():
            ln = ln.split("#")[0].strip()
            if not ln:
                continue
            name = ln
            for sep in ("==", ">=", "<=", "~=", ">", "<", "["):
                name = name.split(sep)[0]
            name = name.strip()
            if importlib.util.find_spec(mods.get(name.lower(), name.replace("-", "_"))) is None:
                return True
    except Exception:
        return True
    return False


def get_cuda_status() -> Dict[str, Any]:
    """Current PyTorch/GPU status and what the installer would propose."""
    info = detect_system()
    needed, why = plan.training_needed(info)
    status: Dict[str, Any] = {
        "cuda_available": False,
        "device_name": "N/D",
        "torch_version": "Non installato",
        "has_nvidia_driver": info.nvidia,
        "gpu_name": info.gpu_name,
        "apple_silicon": info.apple_silicon,
        "training_installed": state.is_installed("training"),
        "install_needed": False,
        "install_note": why,
        "install_variant": "",
        "extras_pending": False,
    }
    try:
        import torch
        status["torch_version"] = torch.__version__
        status["cuda_available"] = torch.cuda.is_available()
        if status["cuda_available"]:
            status["device_name"] = torch.cuda.get_device_name(0)
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            status["device_name"] = "Apple GPU (MPS)"
    except ImportError:
        pass

    if needed and status["cuda_available"] and not status["training_installed"] and _training_extras_missing():
        status["extras_pending"] = True  # GPU already active: only the training extras remain
    if needed and not status["cuda_available"]:
        status["install_needed"] = True
        status["install_variant"] = plan.training_torch_candidates(info)[0].label
    return status


def launch_training_installer() -> bool:
    """
    Starts the installation of the training components in a detached process that
    waits for this app to close, installs, and reopens it by itself.
    Returns True if the process started (the caller must close the app).
    """
    os_name = detect_system().os_name
    py = state.venv_python(os_name)
    if not py.exists():
        py = Path(sys.executable)
    cmd = [str(py), "-m", "common.ambient.installer", "--os", os_name, "--component", "training",
           "--yes", "--relaunch", "--wait-pid", str(os.getpid())]
    try:
        subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), **DETACHED_HIDDEN)      # no console window
        return True
    except Exception:
        return False
