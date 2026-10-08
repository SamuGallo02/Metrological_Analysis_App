"""
Stato dell'accelerazione hardware e avvio dell'installazione dei componenti di
training. L'installazione vera e propria e' in installer/ (processo separato:
PyTorch non si puo' sostituire mentre l'app lo ha gia' caricato in memoria).

Autore: Samuele Gallo
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from installer import plan, state
from installer.sysinfo import detect_system

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_cuda_status() -> Dict[str, Any]:
    """Stato corrente di PyTorch/GPU e di cosa l'installer proporrebbe."""
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

    if needed and status["cuda_available"] and not status["training_installed"]:
        status["extras_pending"] = True  # GPU gia' attiva: restano solo gli extra del training
    if needed and not status["cuda_available"]:
        status["install_needed"] = True
        status["install_variant"] = plan.training_torch_candidates(info)[0].label
    return status


def launch_training_installer() -> bool:
    """
    Avvia l'installazione dei componenti di training in un processo staccato che
    attende la chiusura di questa app, installa e la riapre da solo.
    Ritorna True se il processo e' partito (il chiamante deve chiudere l'app).
    """
    os_name = detect_system().os_name
    py = state.venv_python(os_name)
    if not py.exists():
        py = Path(sys.executable)
    cmd = [str(py), "-m", "installer", "--os", os_name, "--component", "training",
           "--yes", "--relaunch", "--wait-pid", str(os.getpid())]
    try:
        if os.name == "nt":
            # finestra di console visibile: l'utente vede l'avanzamento del download
            subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), creationflags=0x00000010, close_fds=True)  # CREATE_NEW_CONSOLE
        else:
            subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), start_new_session=True, close_fds=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False
