"""Logica di installazione dei componenti 'core' e 'training'."""

from __future__ import annotations

import argparse
import math
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple

from . import plan, state
from .sysinfo import OS_LINUX, OS_MACOS, OS_WINDOWS, SystemInfo, detect_system

ROOT = state.PROJECT_ROOT
LOG_FILE = ROOT / "install_log.txt"
MIN_PY = (3, 10)
CORE_IMPORTS = "import PySide6, cv2, numpy, pandas, torch, ultralytics"
# su Windows nessuna finestra di console per i sottoprocessi
_NOWIN = {"creationflags": 0x08000000} if os.name == "nt" else {}


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


SIZE_RE = re.compile(r"\(([\d.]+)\s*(kB|MB|GB)\)")
PROGRESS_RE = re.compile(r"Progress\s+(\d+)\s+of\s+(\d+)")


class Installer:
    def __init__(self, os_name: str, dry_run: bool = False, progress: bool = False):
        self.os_name = os_name
        self.dry = dry_run
        self.progress = progress
        self.info: SystemInfo = detect_system()
        self.vpy = state.venv_python(os_name)

    # ---- avanzamento (letto dalla finestra grafica dell'installer) ----------
    def report(self, pct: float, text: str = "") -> None:
        if self.progress:
            say(f"@@PROGRESS {int(max(0, min(100, pct)))} {text}")

    # ---- esecuzione comandi -------------------------------------------------
    def run(self, cmd: List[str], check: bool = True) -> int:
        say("  > " + " ".join(str(c) for c in cmd))
        if self.dry:
            return 0
        rc = subprocess.call([str(c) for c in cmd], cwd=str(ROOT), **_NOWIN)
        if check and rc != 0:
            raise RuntimeError(f"comando fallito (codice {rc})")
        return rc

    def pip(self, *args: str, check: bool = True, span: Tuple[float, float] = (0, 0)) -> int:
        """Esegue pip mostrando l'avanzamento: 'span' e' l'intervallo (%) che questo comando
        occupa nella barra complessiva."""
        lo, hi = span
        base = [str(self.vpy), "-m", "pip", *map(str, args)]
        if self.dry:
            say("  > " + " ".join(base))
            return 0
        use_raw = False  # "--progress-bar raw" esiste solo in pip recenti; basta la stima a tempo
        for attempt in (0, 1):
            cmd = base + (["--progress-bar", "raw"] if use_raw and attempt == 0 else [])
            say("  > " + " ".join(cmd))
            proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace", **_NOWIN)
            steps, last, invalid = 0, -1, False
            big_t0, big_size = 0.0, 0.0       # download grosso in corso (inizio, byte)
            lines: "queue.Queue" = queue.Queue()

            def _reader(pipe=proc.stdout, q=lines):
                for ln in pipe:
                    q.put(ln.rstrip())
                q.put(None)

            threading.Thread(target=_reader, daemon=True).start()
            finished = False
            while not finished:
                try:
                    line = lines.get(timeout=1.0)
                except queue.Empty:
                    line = ""
                    # nessuna riga nuova: durante un download grosso la barra avanza col tempo
                    # (stima a ~6 MB/s) cosi' non resta ferma per minuti
                    if big_size and hi > lo:
                        T = max(big_size / 6e6, 5.0)
                        frac = min(0.92, 1 - math.exp(-(time.time() - big_t0) / T))
                        pct = lo + (hi - lo) * (0.05 + 0.85 * frac)
                        if int(pct) > last:
                            last = int(pct)
                            self.report(pct, "Download dei componenti")
                    continue
                if line is None:
                    finished = True
                    continue
                if "invalid choice" in line and "progress" in line.lower():
                    invalid = True
                m = PROGRESS_RE.search(line)
                if m:
                    done, total = int(m.group(1)), int(m.group(2))
                    if total >= 50_000_000 and hi > lo:        # pip recente: avanzamento reale
                        big_size = 0.0
                        pct = lo + (hi - lo) * (0.05 + 0.85 * done / total)
                        if int(pct) > last:
                            last = int(pct)
                            self.report(pct, "Download dei componenti")
                    continue
                say(line)
                sz = SIZE_RE.search(line) if line.startswith("Downloading") else None
                if sz:
                    mult = {"kB": 1e3, "MB": 1e6, "GB": 1e9}[sz.group(2)]
                    if float(sz.group(1)) * mult >= 50e6:
                        big_t0, big_size = time.time(), float(sz.group(1)) * mult
                if line.startswith("Installing collected"):
                    big_size = 0.0
                if hi > lo and line.startswith(("Collecting", "Downloading", "Installing collected")):
                    steps += 1
                    pct = lo + (hi - lo) * 0.95 * (1 - 0.9 ** steps)
                    if line.startswith("Installing collected"):
                        pct = max(pct, lo + (hi - lo) * 0.92)
                    if int(pct) > last:
                        last = int(pct)
                        self.report(pct, line[:70])
            rc = proc.wait()
            if rc != 0 and invalid and attempt == 0:
                continue        # pip troppo vecchio per '--progress-bar raw': riprova senza
            break
        if hi > lo:
            self.report(hi)
        if check and rc != 0:
            raise RuntimeError(f"pip terminato con codice {rc}")
        return rc

    # ---- venv ---------------------------------------------------------------
    def ensure_venv(self) -> None:
        if self.vpy.exists():
            say("[OK] Ambiente virtuale gia' presente: lo riutilizzo.")
            return
        say(f"[..] Creo l'ambiente virtuale in {state.venv_dir(self.os_name).name} ...")
        self.run([sys.executable, "-m", "venv", state.venv_dir(self.os_name)])

    def _venv_eval(self, code: str) -> str:
        if self.dry or not self.vpy.exists():
            return ""
        try:
            r = subprocess.run([str(self.vpy), "-c", code], capture_output=True, text=True, timeout=120, **_NOWIN)
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""

    def venv_has_core(self) -> bool:
        if self.dry or not self.vpy.exists():
            return False
        return subprocess.call([str(self.vpy), "-c", CORE_IMPORTS],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **_NOWIN) == 0

    def torch_matches_target(self) -> bool:
        """True se il PyTorch gia' presente va bene per questo hardware (niente da reinstallare)."""
        ver = self._venv_eval("import torch; print(torch.__version__)")
        if not ver:
            return False
        wants_gpu = bool(plan.training_torch_candidates(self.info))
        return ("+cu" in ver) or not wants_gpu

    # ---- torch --------------------------------------------------------------
    def install_best_torch(self, span: Tuple[float, float]) -> "plan.TorchChoice":
        """GPU NVIDIA => build CUDA compatibile col driver (con ripiego sulle precedenti
        e, in ultima istanza, sulla CPU); altrimenti la build giusta per il sistema."""
        candidates = plan.training_torch_candidates(self.info)
        for c in candidates:
            say(f"[2/3] Installo PyTorch con supporto GPU ({c.label}, {plan.SIZE_HINT['cuda']}) ...")
            self.pip("uninstall", "-y", "torch", "torchvision", check=False)
            if self.pip("install", "torch", "torchvision", "--index-url", c.index_url, check=False, span=span) == 0:
                return c
            say(f"[ATTENZIONE] Build {c.label} non installabile, provo la precedente ...")
        if candidates:
            say("[ATTENZIONE] Nessuna build GPU installabile: uso la versione CPU (potrai riprovare dall'app).")
        choice = plan.core_torch(self.info)
        say(f"[2/3] Installo PyTorch ({choice.label}, {plan.SIZE_HINT.get(choice.label, '')}) ...")
        args = ["install", "torch", "torchvision"] + (["--index-url", choice.index_url] if choice.index_url else [])
        self.pip(*args, span=span)
        return choice

    # ---- core ---------------------------------------------------------------
    def install_core(self, force: bool = False) -> None:
        say(f"[INFO] Sistema: {self.info.describe()}")
        self.report(1, "Controllo dei componenti gia' presenti")

        # Tutto gia' a posto (anche da installazioni precedenti): non si tocca nulla.
        if not force and self.venv_has_core() and self.torch_matches_target():
            say("[OK] Componenti gia' installati e adatti a questo computer: nulla da fare.")
            if not self.dry:
                torch_ver = self._venv_eval("import torch; print(torch.__version__)")
                label = "cu" + torch_ver.split("+cu")[1] if "+cu" in torch_ver else "esistente"
                state.mark_component("core", os=self.os_name, torch=label,
                                     python=".".join(map(str, self.info.python)))
            self.report(100, "Componenti gia' presenti")
            return

        self.ensure_venv()
        self.report(4, "Ambiente virtuale pronto")

        if not force and self.torch_matches_target():
            say("[OK] PyTorch gia' presente e adatto: lo mantengo.")
            ver = self._venv_eval("import torch; print(torch.__version__)")
            choice = plan.TorchChoice("cu" + ver.split("+cu")[1] if "+cu" in ver else "esistente", None)
            self.report(70, "PyTorch gia' presente")
        else:
            # PyTorch PRIMA di ultralytics: cosi' pip lo considera gia' soddisfatto e non
            # scarica da PyPI una build diversa da quella scelta per questo hardware.
            choice = self.install_best_torch(span=(5, 70))

        say("[3/3] Installo le librerie mancanti (requirements.txt) ...")
        self.pip("install", "-r", ROOT / "requirements.txt", span=(70, 97))  # pip salta cio' che c'e' gia'

        if not self.dry:
            self.report(98, "Verifica finale")
            if not self.venv_has_core():
                raise RuntimeError("verifica finale fallita: import dei moduli base non riuscito")
            state.mark_component("core", os=self.os_name, torch=choice.label,
                                 python=".".join(map(str, self.info.python)))
        self.report(100, "Installazione completata")
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

        variant = state.load().get("core", {}).get("torch", "")
        if variant.startswith("cu"):
            say(f"[OK] PyTorch con GPU ({variant}) gia' presente: non lo reinstallo.")
        else:
            variant = ""
            for c in plan.training_torch_candidates(self.info):
                say(f"[1/2] Installo PyTorch con supporto GPU ({c.label}, {plan.SIZE_HINT['cuda']}) ...")
                self.pip("uninstall", "-y", "torch", "torchvision", check=False)
                if self.pip("install", "torch", "torchvision", "--index-url", c.index_url, check=False) == 0:
                    variant = c.label
                    break
                say(f"[ATTENZIONE] Build {c.label} non installabile, provo la precedente ...")
            if not variant:
                say("[ERRORE] Nessuna build CUDA installabile: ripristino la versione CPU per non rompere l'app.")
                choice = plan.core_torch(self.info)
                args = ["install", "torch", "torchvision"] + (["--index-url", choice.index_url] if choice.index_url else [])
                self.pip(*args, check=False)
                raise RuntimeError("installazione CUDA non riuscita")

        extra = ROOT / "requirements-training.txt"
        if extra.exists() and any(l.strip() and not l.lstrip().startswith("#")
                                  for l in extra.read_text(encoding="utf-8").splitlines()):
            say("[2/2] Installo gli extra per il training (requirements-training.txt) ...")
            self.pip("install", "-r", extra)

        if not self.dry:
            data = state.load()
            if variant and data.get("core"):
                data["core"]["torch"] = variant
                state.save(data)
            state.mark_component("training", torch=variant)
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
    ap.add_argument("--progress", action="store_true", help="stampa righe '@@PROGRESS n testo' per la GUI")
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

    inst = Installer(os_name, a.dry_run, a.progress)

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
            args += ["--progress"] if a.progress else []
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
