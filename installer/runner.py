"""Logica di installazione dei componenti 'core' e 'training'."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from . import plan, state
from .sysinfo import OS_LINUX, OS_MACOS, OS_WINDOWS, SystemInfo, detect_system

ROOT = state.PROJECT_ROOT
LOG_FILE = ROOT / "install_log.txt"
MIN_PY = (3, 10)
CORE_IMPORTS = "import PySide6, cv2, numpy, pandas, torch, ultralytics"


class Tee:
    """Scrive su console e su install_log.txt."""

    def __init__(self, path: Path):
        self.f = open(path, "a", encoding="utf-8", errors="replace")
        self.out = sys.stdout

    def write(self, s):
        try:
            self.out.write(s)
        except Exception:
            pass
        self.f.write(s)
        self.f.flush()

    def flush(self):
        try:
            self.out.flush()
        except Exception:
            pass
        self.f.flush()


def say(msg: str = "") -> None:
    print(msg, flush=True)


class Installer:
    def __init__(self, os_name: str, dry_run: bool = False):
        self.os_name = os_name
        self.dry = dry_run
        self.info: SystemInfo = detect_system()
        self.vpy = state.venv_python(os_name)

    # ---- esecuzione comandi -------------------------------------------------
    def run(self, cmd: List[str], check: bool = True) -> int:
        say("  > " + " ".join(str(c) for c in cmd))
        if self.dry:
            return 0
        rc = subprocess.call([str(c) for c in cmd], cwd=str(ROOT))
        if check and rc != 0:
            raise RuntimeError(f"comando fallito (codice {rc})")
        return rc

    def pip(self, *args: str, check: bool = True) -> int:
        return self.run([self.vpy, "-m", "pip", *args], check=check)

    # ---- venv ---------------------------------------------------------------
    def ensure_venv(self) -> None:
        if self.vpy.exists():
            return
        say(f"[..] Creo l'ambiente virtuale in {state.venv_dir(self.os_name).name} ...")
        self.run([sys.executable, "-m", "venv", state.venv_dir(self.os_name)])

    def venv_has_core(self) -> bool:
        if self.dry or not self.vpy.exists():
            return False
        return subprocess.call([str(self.vpy), "-c", CORE_IMPORTS],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0

    # ---- core ---------------------------------------------------------------
    def install_core(self, force: bool = False) -> None:
        say(f"[INFO] Sistema: {self.info.describe()}")
        if not force and state.is_installed("core") and self.venv_has_core():
            say("[OK] Componenti base gia' installati: nessuna operazione necessaria.")
            return

        self.ensure_venv()
        choice = plan.core_torch(self.info)
        say(f"[1/3] Aggiorno pip ...")
        self.pip("install", "--upgrade", "pip")

        # PyTorch PRIMA di ultralytics: cosi' pip lo considera gia' soddisfatto e non
        # scarica da PyPI la build CUDA (multi-GB su Linux) che non serve.
        say(f"[2/3] Installo PyTorch ({choice.label}, {plan.SIZE_HINT.get(choice.label, '')}) ...")
        args = ["install", "torch", "torchvision"]
        if choice.index_url:
            args += ["--index-url", choice.index_url]
        self.pip(*args)

        say("[3/3] Installo le librerie dell'applicativo (requirements.txt) ...")
        self.pip("install", "-r", ROOT / "requirements.txt")

        if not self.dry:
            if not self.venv_has_core():
                raise RuntimeError("verifica finale fallita: import dei moduli base non riuscito")
            state.mark_component("core", os=self.os_name, torch=choice.label,
                                 python=".".join(map(str, self.info.python)))
        say("[OK] Installazione dei componenti base completata.")

    # ---- training -----------------------------------------------------------
    def install_training(self) -> None:
        say(f"[INFO] Sistema: {self.info.describe()}")
        needed, why = plan.training_needed(self.info)
        if not needed:
            say(f"[OK] {why}")
            if not self.dry:
                state.mark_component("training", torch="none", note=why)
            return

        candidates = plan.training_torch_candidates(self.info)
        extra = ROOT / "requirements-training.txt"
        installed: Optional[str] = None
        for c in candidates:
            say(f"[1/2] Installo PyTorch con supporto GPU ({c.label}, {plan.SIZE_HINT['cuda']}) ...")
            self.pip("uninstall", "-y", "torch", "torchvision", check=False)
            if self.pip("install", "torch", "torchvision", "--index-url", c.index_url, check=False) == 0:
                installed = c.label
                break
            say(f"[ATTENZIONE] Build {c.label} non installabile, provo la precedente ...")

        if not installed:
            say("[ERRORE] Nessuna build CUDA installabile: ripristino la versione CPU per non rompere l'app.")
            choice = plan.core_torch(self.info)
            args = ["install", "torch", "torchvision"] + (["--index-url", choice.index_url] if choice.index_url else [])
            self.pip(*args, check=False)
            raise RuntimeError("installazione CUDA non riuscita")

        if extra.exists() and any(l.strip() and not l.lstrip().startswith("#")
                                  for l in extra.read_text(encoding="utf-8").splitlines()):
            say("[2/2] Installo gli extra per il training (requirements-training.txt) ...")
            self.pip("install", "-r", extra)

        if not self.dry:
            state.mark_component("training", torch=installed)
        say("[OK] Componenti di training installati.")


# ---- utilita' per il riavvio dell'app (installazione lanciata dalla GUI) -----
def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def wait_for_exit(pid: int, timeout: float = 60.0) -> None:
    end = time.time() + timeout
    while _pid_alive(pid) and time.time() < end:
        time.sleep(0.3)


def relaunch_app(os_name: str) -> None:
    py = state.venv_gui_python(os_name)
    cmd = [str(py), str(ROOT / "main.py")]
    if os_name == OS_WINDOWS:
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(cmd, cwd=str(ROOT), creationflags=flags, close_fds=True)
    else:
        subprocess.Popen(cmd, cwd=str(ROOT), start_new_session=True, close_fds=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def notify(os_name: str, text: str) -> None:
    """Notifica best-effort (utile quando l'installazione gira senza finestra)."""
    try:
        if os_name == OS_MACOS:
            subprocess.call(["osascript", "-e", f'display notification "{text}" with title "Analisi Metrologica"'])
        elif os_name == OS_LINUX:
            subprocess.call(["notify-send", "Analisi Metrologica", text])
    except Exception:
        pass


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="installer", description="Installer Analisi Metrologica")
    ap.add_argument("--os", choices=["auto", OS_WINDOWS, OS_MACOS, OS_LINUX], default="auto",
                    help="sistema operativo scelto (default: rilevato)")
    ap.add_argument("--component", choices=["core", "training"], default="core")
    ap.add_argument("--force", action="store_true", help="reinstalla anche se risulta gia' tutto a posto")
    ap.add_argument("--dry-run", action="store_true", help="mostra i comandi senza eseguirli")
    ap.add_argument("--wait-pid", type=int, default=0, help="attende la chiusura di questo processo (app)")
    ap.add_argument("--relaunch", action="store_true", help="riavvia l'app al termine")
    ap.add_argument("--yes", action="store_true", help="non chiede conferme")
    a = ap.parse_args(argv)

    detected = detect_system().os_name
    os_name = detected if a.os == "auto" else a.os
    if os_name != detected:
        print(f"[ERRORE] Hai scelto l'installer per '{os_name}' ma questo computer e' '{detected}'. "
              f"Usa l'installer per {detected}.")
        return 2
    if sys.version_info < MIN_PY:
        print(f"[ERRORE] Serve Python {MIN_PY[0]}.{MIN_PY[1]} o successivo.")
        return 2

    sys.stdout = sys.stderr = Tee(LOG_FILE)
    say(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} - installer ({a.component}) =====")

    inst = Installer(os_name, a.dry_run)

    # Se non siamo gia' nel venv di progetto, lo creiamo e rilanciamo l'installer li'.
    in_venv = Path(sys.prefix).resolve() == state.venv_dir(os_name).resolve()
    rc = 0
    try:
        if a.wait_pid:
            say("[..] Attendo la chiusura dell'applicativo ...")
            wait_for_exit(a.wait_pid)
        if a.component == "core" and not in_venv and not a.dry_run:
            inst.ensure_venv()
            args = [str(inst.vpy), "-m", "installer", "--os", os_name, "--component", "core", "--yes"]
            args += ["--force"] if a.force else []
            return subprocess.call(args, cwd=str(ROOT))
        if a.component == "core":
            inst.install_core(a.force)
        else:
            legacy = (state.venv_dir(os_name) / ".setup_complete").exists()  # installazioni precedenti
            if not (state.is_installed("core") or legacy) and not a.dry_run:
                say("[ERRORE] Installa prima i componenti base (installer per il tuo sistema).")
                return 1
            inst.install_training()
    except Exception as e:
        say(f"[ERRORE] {e}")
        say(f"Dettagli completi in: {LOG_FILE}")
        rc = 1

    if a.component == "training":
        notify(os_name, "Installazione componenti di training " + ("completata" if rc == 0 else "NON riuscita"))
    if a.relaunch and not a.dry_run:
        relaunch_app(os_name)
    return rc
