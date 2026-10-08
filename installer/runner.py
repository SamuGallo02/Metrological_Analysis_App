"""Logica di installazione dei componenti 'core' e 'training'."""

from __future__ import annotations

import argparse
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


GPU_NEED_GB = 10.0   # picco su disco per PyTorch CUDA: download + installazione + margine
CPU_NEED_GB = 3.0
TMP_DIR = ROOT / ".tmp"


IMPORT_NAMES = {"PySide6": "PySide6.QtWidgets", "opencv-python": "cv2", "pyyaml": "yaml", "pillow": "PIL", "nvidia-ml-py": "pynvml",
                "scikit-learn": "sklearn", "python-dateutil": "dateutil"}


def parse_requirements(path: Path) -> List[str]:
    """Nomi dei pacchetti di un requirements.txt (senza versioni, commenti e opzioni)."""
    names: List[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line and not line.startswith("-"):
                names.append(re.split(r"[<>=!~;\[ ]", line, maxsplit=1)[0])
    return names


def requirement_lines(path: Path) -> List[Tuple[str, str]]:
    """[(nome, riga completa con eventuale versione minima)] da un requirements.txt."""
    out: List[Tuple[str, str]] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line and not line.startswith("-"):
                out.append((re.split(r"[<>=!~;\[ ]", line, maxsplit=1)[0], line))
    return out


def import_name(pip_name: str) -> str:
    for k, v in IMPORT_NAMES.items():
        if k.lower() == pip_name.lower():
            return v
    return pip_name.replace("-", "_")


def free_gb(path: Path) -> float:
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(str(p)).free / 1e9


SIZE_RE = re.compile(r"\(([\d.]+)\s*(kB|MB|GB)\)")
PROGRESS_RE = re.compile(r"Progress\s+(\d+)\s+of\s+(\d+)")


class Installer:
    def __init__(self, os_name: str, dry_run: bool = False, progress: bool = False):
        self.os_name = os_name
        self.dry = dry_run
        self.progress = progress
        self.info: SystemInfo = detect_system()
        self.vpy = state.venv_python(os_name)
        self.disk_full = False       # pip ha segnalato "No space left on device"
        self.skipped_space = False   # build GPU saltata per spazio insufficiente (si riprovera' in futuro)

    # ---- avanzamento (letto dalla finestra grafica dell'installer) ----------
    def warn(self, text: str) -> None:
        say(f"[ATTENZIONE] {text}")
        if self.progress:
            say(f"@@WARN {text}")

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

    def pip(self, *args: str, check: bool = True, span: Tuple[float, float] = (0, 0),
            nocache: bool = False) -> int:
        """Esegue pip mostrando l'avanzamento: 'span' e' l'intervallo (%) che questo comando
        occupa nella barra complessiva."""
        lo, hi = span
        base = [str(self.vpy), "-m", "pip", *map(str, args)]
        if nocache:
            # i wheel da GB non vanno nella cache di pip: raddoppierebbero lo spazio usato e pip
            # puo' andare in MemoryError rileggendoli (visto con PyTorch CUDA)
            base.insert(4, "--no-cache-dir")
        # file temporanei di pip sul disco scelto per l'installazione, non su quello di sistema
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, TMP=str(TMP_DIR), TEMP=str(TMP_DIR), TMPDIR=str(TMP_DIR))
        if self.dry:
            say("  > " + " ".join(base))
            return 0
        use_raw = False  # "--progress-bar raw" esiste solo in pip recenti; basta la stima a tempo
        for attempt in (0, 1):
            cmd = base + (["--progress-bar", "raw"] if use_raw and attempt == 0 else [])
            say("  > " + " ".join(cmd))
            proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace", env=env, **_NOWIN)
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
                if "No space left on device" in line or "Errno 28" in line:
                    self.disk_full = True
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

    # stati possibili di un componente
    OK, MISSING, BROKEN, OLD = "ok", "missing", "broken", "old"

    def component_status(self, reqs: List[Tuple[str, str]], light: bool = False) -> Dict[str, Tuple[Optional[str], str]]:
        """Per ogni componente (nome, requisito): (versione installata, stato) con stato
        ok / missing (non installato) / broken (installato ma non importabile) /
        old (versione sotto il minimo richiesto). 'light' salta il test di import."""
        if self.dry or not self.vpy.exists() or not reqs:
            return {n: (None, self.MISSING) for n, _ in reqs}
        code = ("import importlib, importlib.metadata as m, json, sys\n"
                "light = sys.argv[2] == '1'\n"
                "try:\n"
                "    from pip._vendor.packaging.specifiers import SpecifierSet\n"
                "    from pip._vendor.packaging.version import Version\n"
                "except Exception:\n"
                "    SpecifierSet = None\n"
                "out = {}\n"
                "for pip, mod, spec in json.loads(sys.argv[1]):\n"
                "    try: ver = m.version(pip)\n"
                "    except Exception: out[pip] = [None, 'missing']; continue\n"
                "    if not light:\n"
                "        try: importlib.import_module(mod)\n"
                "        except BaseException: out[pip] = [ver, 'broken']; continue\n"
                "    state = 'ok'\n"
                "    if spec and SpecifierSet is not None:\n"
                "        try:\n"
                "            if not SpecifierSet(spec).contains(Version(ver), prereleases=True): state = 'old'\n"
                "        except Exception: pass\n"
                "    out[pip] = [ver, state]\n"
                "print(json.dumps(out))")
        pairs = json.dumps([[n, import_name(n), line[len(n):].strip()] for n, line in reqs])
        try:
            r = subprocess.run([str(self.vpy), "-c", code, pairs, "1" if light else "0"], capture_output=True,
                               text=True, timeout=600, **_NOWIN)
            data = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 and r.stdout.strip() else None
        except Exception:
            data = None
        if data is None:
            if not light:   # import troppo lento o crash: ripiego sul controllo leggero (mai "tutto da reinstallare")
                say("[ATTENZIONE] Test di import non riuscito: uso il controllo leggero dei componenti.")
                return self.component_status(reqs, light=True)
            return {n: (None, self.MISSING) for n, _ in reqs}
        return {n: (tuple(data[n]) if n in data else (None, self.MISSING)) for n, _ in reqs}

    def show_status(self, status: Dict[str, Tuple[Optional[str], str]]) -> None:
        labels = {self.OK: "gia' presente", self.MISSING: "DA INSTALLARE", self.BROKEN: "DANNEGGIATO (reinstallo)",
                  self.OLD: "TROPPO VECCHIO (aggiorno)"}
        say("[INFO] Stato dei componenti:")
        for n, (ver, st) in status.items():
            say(f"   {n:<16} {labels[st]}" + (f" [{ver}]" if ver else ""))

    def fix_dependencies(self) -> None:
        """Dipendenze indirette: 'pip check' segnala quelle mancanti o in conflitto e le ripara.
        Non tocca mai torch/torchvision (per non sostituire la build scelta per la GPU)."""
        if self.dry:
            return
        protected = {"torch", "torchvision", "torchaudio"}
        for attempt in range(2):
            r = subprocess.run([str(self.vpy), "-m", "pip", "check"], capture_output=True, text=True,
                               timeout=300, **_NOWIN)
            if r.returncode == 0:
                say("[OK] Coerenza delle dipendenze verificata (pip check): nessun problema.")
                return
            todo = set()
            for line in r.stdout.splitlines():
                m = (re.search(r"requires (.+?), which is not installed", line)
                     or re.search(r"has requirement (.+?), but you have", line))
                if m and re.split(r"[<>=!~; \[]", m.group(1).strip(), maxsplit=1)[0].lower() not in protected:
                    todo.add(m.group(1).strip())
            if not todo:
                self.warn("pip check segnala incongruenze che non posso riparare da solo: "
                          + " | ".join(r.stdout.strip().splitlines()[:3]))
                return
            say(f"[..] Ripristino le dipendenze indirette: {', '.join(sorted(todo))} ...")
            self.pip("install", *sorted(todo), check=False)
        self.warn("Alcune dipendenze indirette restano incongruenti (vedi il log).")

    def installed_torch_index(self) -> Optional[str]:
        """Indice PyTorch coerente con la build di torch gia' installata (per aggiungere torchvision uguale)."""
        ver = self._venv_eval("import torch; print(torch.__version__)")
        if "+" in ver:
            return plan.PYTORCH_INDEX + ver.split("+", 1)[1]
        return None

    def torch_matches_target(self) -> bool:
        """True se il PyTorch gia' presente va bene per questo hardware (niente da reinstallare)."""
        ver = self._venv_eval("import torch; print(torch.__version__)")
        if not ver:
            return False
        if not plan.training_torch_candidates(self.info):
            return True                      # niente GPU NVIDIA: qualunque build funzionante va bene
        if "+cu" in ver:
            return self.cuda_works()         # build CUDA gia' presente: la teniamo se funziona
        # build senza CUDA (es. PyPI su Windows): serve la GPU solo se una build CUDA e' davvero utilizzabile;
        # se un tentativo precedente ha gia' ripiegato sulla CPU lo ricordiamo nello stato
        return bool(state.load().get("core", {}).get("gpu_unsupported"))

    # ---- torch --------------------------------------------------------------
    def cuda_works(self) -> bool:
        """True se PyTorch riesce davvero a usare la GPU (non basta che il pacchetto sia installato:
        le build recenti possono non supportare GPU vecchie)."""
        if self.dry:
            return True
        return bool(self._venv_eval("import torch; torch.zeros(1).cuda(); print(torch.cuda.get_device_name(0))"))

    def install_gpu_torch(self, span: Tuple[float, float]) -> Optional[str]:
        """Prova le build CUDA compatibili col driver, dalla piu' recente; ritorna l'etichetta di
        quella che funziona davvero, oppure None. Non disinstalla prima: pip scarica la nuova
        build e sostituisce la vecchia solo a download finito (--force-reinstall serve perche'
        '2.x' e '2.x+cu126' sembrerebbero la stessa versione)."""
        for c in plan.training_torch_candidates(self.info):
            say(f"[2/3] Installo PyTorch con supporto GPU ({c.label}, {plan.SIZE_HINT['cuda']}) ...")
            rc = self.pip("install", "--force-reinstall", "torch", "torchvision", "--index-url", c.index_url,
                          check=False, span=span, nocache=True)
            if rc == 0 and self.cuda_works():
                return c.label
            if self.disk_full:
                self.warn("Spazio su disco esaurito durante il download: libera spazio e rilancia l'installer.")
                return None             # riprovare con un'altra build scaricherebbe di nuovo GB inutilmente
            say(f"[ATTENZIONE] Build {c.label} non utilizzabile su questa GPU, provo la precedente ...")
        return None

    def install_best_torch(self, span: Tuple[float, float]) -> "plan.TorchChoice":
        """GPU NVIDIA => build CUDA che funziona davvero; altrimenti (o se nessuna funziona)
        la build CPU/standard adatta al sistema."""
        if plan.training_torch_candidates(self.info):
            free = free_gb(ROOT)
            if free < GPU_NEED_GB:
                self.skipped_space = True
                self.warn(f"Spazio libero {free:.1f} GB: per PyTorch con GPU ne servono circa {GPU_NEED_GB:.0f} GB. "
                          "Installo la versione CPU; libera spazio e rilancia l'installer per attivare la GPU.")
            else:
                label = self.install_gpu_torch(span)
                if label:
                    return plan.TorchChoice(label, None)
                if not self.disk_full:
                    self.warn("Nessuna build GPU utilizzabile con questa scheda: uso la versione CPU.")
        choice = plan.core_torch(self.info)
        say(f"[2/3] Installo PyTorch ({choice.label}, {plan.SIZE_HINT.get(choice.label, '')}) ...")
        args = ["install", "--force-reinstall", "torch", "torchvision"] + (["--index-url", choice.index_url] if choice.index_url else [])
        self.pip(*args, span=span, nocache=True)
        return choice

    # ---- core ---------------------------------------------------------------
    def install_core(self, force: bool = False) -> None:
        say(f"[INFO] Sistema: {self.info.describe()}")
        self.report(1, "Controllo dei componenti gia' presenti")

        self.ensure_venv()
        self.report(4, "Ambiente virtuale pronto")

        # Controllo di OGNI componente (presenza, integrita', versione minima): si installa solo il necessario.
        reqs = requirement_lines(ROOT / "requirements.txt")
        all_reqs = [("torch", "torch"), ("torchvision", "torchvision")] + reqs
        status = ({n: (None, self.MISSING) for n, _ in all_reqs} if force
                  else self.component_status(all_reqs))
        self.show_status(status)
        self.report(6, "Componenti controllati")

        # --- PyTorch (prima di ultralytics, cosi' pip non ne scarica una build diversa) ---
        torch_ok = status["torch"][1] == self.OK and self.torch_matches_target()
        if torch_ok:
            say(f"[OK] PyTorch {status['torch'][0]} gia' presente e adatto: non lo reinstallo.")
            ver = self._venv_eval("import torch; print(torch.__version__)")
            choice = plan.TorchChoice(("cu" + ver.split("+cu")[1]) if "+cu" in ver else "esistente", None)
            if status["torchvision"][1] != self.OK:
                say("[..] torchvision mancante o danneggiato: lo (re)installo con la stessa build di torch ...")
                idx = self.installed_torch_index()
                self.pip("install", "--force-reinstall", "--no-deps", "torchvision",
                         *(["--index-url", idx] if idx else []), span=(6, 40), nocache=True)
            else:
                say(f"[OK] torchvision {status['torchvision'][0]} gia' presente.")
            self.report(70, "PyTorch gia' presente")
        else:
            choice = self.install_best_torch(span=(6, 70))

        # --- librerie: mancanti/vecchie si installano, danneggiate si reinstallano ---
        todo, broken = [], []
        for n, line in reqs:
            st = status[n][1]
            if st in (self.MISSING, self.OLD):
                todo.append(line)
            elif st == self.BROKEN:
                broken.append(line)
        if todo or broken:
            say(f"[3/3] Installo/aggiorno: {', '.join(l for l in todo + broken)} ...")
            if todo:
                self.pip("install", *(["--upgrade"] if force else []), *todo, span=(70, 90))
            if broken:
                self.pip("install", "--force-reinstall", *broken, span=(90, 96))
        else:
            say("[3/3] Tutte le librerie dell'applicativo sono gia' presenti e integre: nulla da installare.")
        self.report(96, "Librerie a posto")

        # --- dipendenze indirette ---
        self.fix_dependencies()

        if not self.dry:
            self.report(98, "Verifica finale")
            if not self.venv_has_core():
                raise RuntimeError("verifica finale fallita: import dei moduli base non riuscito")
            state.mark_component("core", os=self.os_name, torch=choice.label,
                                 python=".".join(map(str, self.info.python)),
                                 gpu_unsupported=bool(plan.training_torch_candidates(self.info))
                                 and not choice.label.startswith("cu")
                                 and not self.skipped_space and not self.disk_full)
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
        if not (variant.startswith("cu")) and free_gb(ROOT) < GPU_NEED_GB:
            raise RuntimeError(f"Spazio libero insufficiente ({free_gb(ROOT):.1f} GB): servono circa "
                               f"{GPU_NEED_GB:.0f} GB per PyTorch con GPU.")
        if variant.startswith("cu") and self.cuda_works():
            say(f"[OK] PyTorch con GPU ({variant}) gia' presente e funzionante: non lo reinstallo.")
        else:
            variant = self.install_gpu_torch(span=(0, 0)) or ""
            if not variant:
                say("[ERRORE] Nessuna build CUDA utilizzabile con questa GPU: ripristino la versione CPU.")
                choice = plan.core_torch(self.info)
                args = ["install", "--force-reinstall", "torch", "torchvision"] + (["--index-url", choice.index_url] if choice.index_url else [])
                self.pip(*args, check=False)
                data = state.load()
                data.setdefault("core", {})["gpu_unsupported"] = True
                state.save(data)
                raise RuntimeError("GPU non supportata dalle build CUDA attuali di PyTorch")

        extra = requirement_lines(ROOT / "requirements-training.txt")
        if extra:
            st = self.component_status(extra)
            self.show_status(st)
            todo = [line for n, line in extra if st[n][1] in (self.MISSING, self.OLD)]
            broken = [line for n, line in extra if st[n][1] == self.BROKEN]
            if todo:
                say(f"[2/2] Installo gli extra per il training mancanti: {', '.join(todo)} ...")
                self.pip("install", *todo)
            if broken:
                self.pip("install", "--force-reinstall", *broken)
            if not todo and not broken:
                say("[2/2] Extra per il training gia' presenti: nulla da installare.")

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
        if inst.disk_full:
            say("[ERRORE] Spazio su disco esaurito: libera spazio (svuota la cache di pip con "
                f"'{inst.vpy} -m pip cache purge' e i file temporanei) e rilancia l'installer.")
        say(f"[ERRORE] {e}")
        say(f"Dettagli completi in: {LOG_FILE}")
        rc = 1
    finally:
        shutil.rmtree(TMP_DIR, ignore_errors=True)

    if a.component == "training":
        notify(os_name, "Installazione componenti di training " + ("completata" if rc == 0 else "NON riuscita"))
    if a.relaunch and not a.dry_run:
        relaunch_app(os_name)
    return rc
