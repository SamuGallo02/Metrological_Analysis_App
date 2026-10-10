"""Installation logic for the 'core' and 'training' components."""

from __future__ import annotations

import argparse
import json
from urllib.parse import unquote
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

from . import fastdl, integrity, plan, state
from .sysinfo import OS_LINUX, OS_MACOS, OS_WINDOWS, SystemInfo, detect_system

ROOT = state.PROJECT_ROOT
REQUIREMENTS_DIR = Path(__file__).resolve().parent.parent / "requirements"
LOG_FILE = state.VENV_PARENT_DIR / "install_log.txt"
MIN_PY = (3, 10)
CORE_IMPORTS = "import PySide6, cv2, numpy, pandas, torch, ultralytics"
# on Windows, no console window for subprocesses
_NOWIN = {"creationflags": 0x08000000} if os.name == "nt" else {}


class Tee:
    """Writes to the console and to install_log.txt."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
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


GPU_NEED_GB = 10.0   # disk peak for PyTorch CUDA: download + installation + margin
CPU_NEED_GB = 3.0
TMP_DIR = ROOT / ".tmp"
WHEELS_DIR = ROOT / ".wheels"


IMPORT_NAMES = {"PySide6": "PySide6.QtWidgets", "opencv-python": "cv2", "pyyaml": "yaml", "pillow": "PIL", "nvidia-ml-py": "pynvml",
                "scikit-learn": "sklearn", "python-dateutil": "dateutil"}


def parse_requirements(path: Path) -> List[str]:
    """Package names from a requirements.txt (without versions, comments and options)."""
    names: List[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line and not line.startswith("-"):
                names.append(re.split(r"[<>=!~;\[ ]", line, maxsplit=1)[0])
    return names


def requirement_lines(path: Path) -> List[Tuple[str, str]]:
    """[(name, full line with optional minimum version)] from a requirements.txt."""
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
    def __init__(self, os_name: str, dry_run: bool = False, progress: bool = False, cpu_only: bool = False,
                 prefetch: bool = False):
        self.os_name = os_name
        self.dry = dry_run
        self.progress = progress
        self.prefetch = prefetch     # download wheels only (the app is still open with PyTorch loaded)
        self.cpu_only = cpu_only     # the user gives up GPU support (~2.6 GB download)
        self.fast = os.environ.get('AM_NO_FASTDL') != '1'
        self.info: SystemInfo = detect_system()
        self.vpy = state.venv_python(os_name)
        self.gpu_declined = False
        self.disk_full = False       # pip reported "No space left on device"
        self.skipped_space = False   # GPU build skipped for insufficient space (will be retried in the future)

    # ---- progress (read by the installer's graphical window) ---------------
    def warn(self, text: str) -> None:
        say(f"[ATTENZIONE] {text}")
        if self.progress:
            say(f"@@WARN {text}")

    def report(self, pct: float, text: str = "") -> None:
        if self.progress:
            say(f"@@PROGRESS {int(max(0, min(100, pct)))} {text}")

    # ---- command execution --------------------------------------------------
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
        """Runs pip showing progress: 'span' is the interval (%) this command
        occupies in the overall bar."""
        lo, hi = span
        args = tuple(map(str, args))
        if args and args[0] == "install":
            # no .pyc compilation (tens of seconds over thousands of files) and no pip version check
            args = ("install", "--no-compile", "--disable-pip-version-check") + args[1:]
            if self.fast and not self.dry:
                rc = self.fast_install(args, span if hi > lo else (0, 100))
                if rc is not None:
                    if check and rc != 0:
                        raise RuntimeError(f"pip terminato con codice {rc}")
                    return rc
        base = [str(self.vpy), "-m", "pip", *args]
        if nocache:
            # GB-sized wheels must not go in pip's cache: they would double the space used and pip
            # may hit MemoryError when re-reading them (seen with PyTorch CUDA)
            base.insert(4, "--no-cache-dir")
        # pip temporary files on the disk chosen for the installation, not on the system one
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, TMP=str(TMP_DIR), TEMP=str(TMP_DIR), TMPDIR=str(TMP_DIR))
        if self.dry:
            say("  > " + " ".join(base))
            return 0
        use_raw = False  # "--progress-bar raw" exists only in recent pip; the time-based estimate is enough
        for attempt in (0, 1):
            cmd = base + (["--progress-bar", "raw"] if use_raw and attempt == 0 else [])
            say("  > " + " ".join(cmd))
            proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace", env=env, **_NOWIN)
            steps, last, invalid = 0, -1, False
            big_t0, big_size = 0.0, 0.0       # large download in progress (start, bytes)
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
                    # no new line: during a large download the bar advances with time
                    # (estimate at ~6 MB/s) so it does not stay still for minutes
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
                    if total >= 50_000_000 and hi > lo:        # recent pip: real progress
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
                continue        # pip too old for '--progress-bar raw': retry without it
            break
        if hi > lo:
            self.report(hi)
        if check and rc != 0:
            raise RuntimeError(f"pip terminato con codice {rc}")
        return rc

    # ---- fast download ------------------------------------------------------
    def fast_install(self, args: Tuple[str, ...], span: Tuple[float, float],
                     download_only: bool = False) -> Optional[int]:
        """Downloads the wheels in parallel (in segments, with resume and SHA-256 verification) and installs
        them offline. Returns pip's exit code, or None if the method is not applicable and plain
        pip must be used (old pip, sdist, network errors...)."""
        lo, hi = span
        rep = TMP_DIR / "plan.json"
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, TMP=str(TMP_DIR), TEMP=str(TMP_DIR), TMPDIR=str(TMP_DIR))
        try:
            rep.unlink(missing_ok=True)
            r = subprocess.run([str(self.vpy), "-m", "pip", *args, "--no-cache-dir", "--dry-run", "--report", str(rep), "-q"],
                               capture_output=True, text=True, timeout=300, env=env, cwd=str(ROOT), **_NOWIN)
            if r.returncode != 0 or not rep.exists():
                return None
            plan_items = json.loads(rep.read_text(encoding="utf-8")).get("install", [])
            items = []
            for it in plan_items:
                di = it.get("download_info", {})
                url = di.get("url", "")
                if not url.startswith("https://") or not url.split("?")[0].endswith(".whl"):
                    return None            # sdist / local files / VCS: leave it to pip
                items.append({"url": url, "name": unquote(url.split("?")[0].rsplit("/", 1)[-1]),
                              "sha256": di.get("archive_info", {}).get("hashes", {}).get("sha256")})
            if not items:
                return None
        except Exception as e:
            say(f"[INFO] Download veloce non disponibile ({e}): uso pip.")
            return None

        total_mb = 0.0
        last = [-1.0]
        t0 = time.time()

        def on_prog(done: int, total: int) -> None:
            pct = lo + (hi - lo) * (0.05 + 0.85 * done / max(total, 1))
            if int(pct) > last[0] or time.time() - last[0] > 5:
                last[0] = int(pct)
                self.report(pct, f"Download {done / 1e6:.0f} / {total / 1e6:.0f} MB")

        say(f"[..] Download in parallelo di {len(items)} pacchetti ...")
        try:
            files = fastdl.download_many(items, WHEELS_DIR, workers=6, on_progress=on_prog)
        except Exception as e:
            if getattr(e, "errno", None) == 28 or "No space left" in str(e):
                self.disk_full = True
                say("No space left on device")
                return 1
            say(f"[INFO] Download veloce interrotto ({e}): uso pip.")
            return None
        mb = sum(f.stat().st_size for f in files) / 1e6
        say(f"[OK] Scaricati {mb:.0f} MB in {time.time() - t0:.0f} s.")
        if download_only:
            return 0            # the wheels stay in .wheels: the real installation happens when the app restarts

        # offline installation from the files just downloaded (online indexes are removed)
        out, skip = [], False
        for a in args:
            if skip:
                skip = False
                continue
            if a in ("--index-url", "-i", "--extra-index-url"):
                skip = True
                continue
            out.append(a)
        rc = self._pip_stream([str(self.vpy), "-m", "pip", *out, "--no-index", "--find-links", str(WHEELS_DIR)], env)
        if rc == 0:
            shutil.rmtree(WHEELS_DIR, ignore_errors=True)
        return rc

    def _pip_stream(self, cmd: List[str], env: dict) -> int:
        say("  > " + " ".join(cmd))
        proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", env=env, **_NOWIN)
        for ln in proc.stdout:
            ln = ln.rstrip()
            if "No space left on device" in ln or "Errno 28" in ln:
                self.disk_full = True
            say(ln)
        return proc.wait()

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
        return not self.failing_imports()

    def failing_imports(self) -> Dict[str, str]:
        """Tries to import each base module: {module: last line of the error} for those that fail."""
        bad: Dict[str, str] = {}
        for mod in [m.strip() for m in CORE_IMPORTS[len("import "):].split(",")]:
            mod = "PySide6.QtWidgets" if mod == "PySide6" else mod
            r = subprocess.run([str(self.vpy), "-c", f"import {mod}"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", **_NOWIN)
            if r.returncode != 0:
                err = (r.stderr or "").strip()
                say(f"[ERRORE] import {mod} fallito:\n{err[-1500:]}")
                bad[mod] = err.splitlines()[-1] if err else "errore sconosciuto"
        return bad

    def purge_pip_cache(self) -> None:
        """Empties pip's http cache: it may contain GB-sized wheels that cause MemoryError and take up disk."""
        if self.dry or not self.vpy.exists():
            return
        subprocess.run([str(self.vpy), "-m", "pip", "cache", "purge", "--disable-pip-version-check"],
                       capture_output=True, text=True, timeout=120, **_NOWIN)

    # possible states of a component
    OK, MISSING, BROKEN, OLD = "ok", "missing", "broken", "old"

    def component_status(self, reqs: List[Tuple[str, str]], light: bool = False) -> Dict[str, Tuple[Optional[str], str]]:
        """For each component (name, requirement): (installed version, state) with state
        ok / missing (not installed) / broken (installed but not importable) /
        old (version below the required minimum). 'light' skips the import test."""
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
            if not light:   # import too slow or crashed: fall back to the light check (never "reinstall everything")
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
        """Indirect dependencies: 'pip check' reports missing or conflicting ones and repairs them.
        Never touches torch/torchvision (so as not to replace the build chosen for the GPU)."""
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
        """PyTorch index consistent with the already installed torch build (to add a matching torchvision)."""
        ver = self._venv_eval("import torch; print(torch.__version__)")
        if "+" in ver:
            return plan.PYTORCH_INDEX + ver.split("+", 1)[1]
        return None

    def torch_matches_target(self) -> bool:
        """True if the PyTorch already present suits this hardware (nothing to reinstall)."""
        ver = self._venv_eval("import torch; print(torch.__version__)")
        if not ver:
            return False
        if not plan.training_torch_candidates(self.info):
            return True                      # no NVIDIA GPU: any working build is fine
        if "+cu" in ver:
            return self.cuda_works()         # CUDA build already present: keep it if it works
        # build without CUDA (e.g. PyPI on Windows): the GPU is needed only if a CUDA build is actually usable;
        # if a previous attempt already fell back to the CPU we remember it in the state
        return bool(state.load().get("core", {}).get("gpu_unsupported"))

    # ---- torch --------------------------------------------------------------
    def cuda_works(self) -> bool:
        """True if PyTorch can really use the GPU (an installed package is not enough:
        recent builds may not support old GPUs)."""
        if self.dry:
            return True
        return bool(self._venv_eval("import torch; torch.zeros(1).cuda(); print(torch.cuda.get_device_name(0))"))

    def install_gpu_torch(self, span: Tuple[float, float]) -> Optional[str]:
        """Tries the CUDA builds compatible with the driver, from the most recent; returns the label of
        the one that really works, or None. It does not uninstall first: pip downloads the new
        build and replaces the old one only once the download is finished (--force-reinstall is needed because
        '2.x' and '2.x+cu126' would look like the same version)."""
        for c in plan.training_torch_candidates(self.info):
            say(f"[2/3] Installo PyTorch con supporto GPU ({c.label}, {plan.SIZE_HINT['cuda']}) ...")
            rc = self.pip("install", "--force-reinstall", "torch", "torchvision", "--index-url", c.index_url,
                          check=False, span=span, nocache=True)
            if rc == 0 and self.cuda_works():
                return c.label
            if self.disk_full:
                self.warn("Spazio su disco esaurito durante il download: libera spazio e rilancia l'installer.")
                return None             # retrying with another build would needlessly download GBs again
            say(f"[ATTENZIONE] Build {c.label} non utilizzabile su questa GPU, provo la precedente ...")
        return None

    def install_best_torch(self, span: Tuple[float, float]) -> "plan.TorchChoice":
        """NVIDIA GPU => CUDA build that really works; otherwise (or if none works)
        the CPU/standard build suited to the system."""
        if self.cpu_only and plan.training_torch_candidates(self.info):
            self.gpu_declined = True
            say("[INFO] Supporto GPU saltato su richiesta: installo PyTorch CPU (lo si puo' attivare in seguito dalla pagina Training).")
        elif plan.training_torch_candidates(self.info):
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

    # ---- self-repair ----------------------------------------------------------
    def repair(self, deep: bool = False) -> bool:
        """Finds the damaged files of the virtual environment (see integrity.py) and reinstalls ONLY the
        packages they belong to, with the same version (same CUDA build for PyTorch). Returns True if the
        environment is healthy at the end."""
        if not self.vpy.exists():
            say("[ERRORE] Ambiente virtuale assente: usa l'installer completo.")
            return False
        venv = state.venv_dir(self.os_name)
        self.report(2, "Controllo dei file" + (" (completo)" if deep else ""))
        say(f"[..] Controllo l'integrita' dei file in {venv.name} ({'completo, con SHA-256' if deep else 'veloce'}) ...")
        damaged = integrity.scan(venv, deep, lambda i, n: self.report(2 + 28 * i / max(n, 1)))
        if not damaged:
            say("[OK] Tutti i file corrispondono a quanto installato da pip.")
            bad = self.failing_imports() if not self.dry else {}
            if not bad:
                self.report(100, "Ambiente a posto")
                return True
            say("[..] I file sono integri ma alcuni moduli non si importano: ricontrollo le dipendenze ...")
            self.install_core(False)
            return not self.failing_imports()
        for d in damaged.values():
            say(f"[ATTENZIONE] Danneggiato: {d}")
        for round_ in (1, 2):
            names = sorted(damaged)
            for k, name in enumerate(names):
                d = damaged[name]
                span = (30 + 65 * k / len(names), 30 + 65 * (k + 1) / len(names))
                self.report(span[0], f"Reinstallo {d.name}")
                say(f"[..] Reinstallo {d.name}=={d.version} ...")
                index = integrity.torch_index(d.version) if name in ("torch", "torchvision", "torchaudio") else None
                args = ["install", "--force-reinstall", "--no-deps", f"{d.name}=={d.version}"]
                if index:
                    args += ["--index-url", index]
                rc = self.pip(*args, check=False, span=span, nocache=True)
                if rc != 0 and not index:
                    say(f"[ATTENZIONE] Versione {d.version} non disponibile: provo con l'ultima compatibile.")
                    self.pip("install", "--force-reinstall", "--no-deps", d.name, check=False, span=span, nocache=True)
                if self.disk_full:
                    say("[ERRORE] Spazio su disco esaurito: libera spazio e rilancia la riparazione.")
                    return False
            damaged = integrity.scan(venv, deep)
            if not damaged:
                break
            say(f"[ATTENZIONE] Dopo la riparazione restano da sistemare: {', '.join(sorted(damaged))}"
                + (" - riprovo." if round_ == 1 else ""))
        if damaged:
            say("[ERRORE] Alcuni file restano danneggiati: " + "; ".join(str(d) for d in damaged.values()))
            return False
        bad = self.failing_imports()
        self.report(100, "Riparazione completata" if not bad else "Riparazione incompleta")
        say("[OK] Riparazione completata." if not bad else "[ERRORE] Moduli ancora non importabili: " + ", ".join(bad))
        return not bad

    # ---- core ---------------------------------------------------------------
    def install_core(self, force: bool = False) -> None:
        say(f"[INFO] Sistema: {self.info.describe()}")
        self.report(1, "Controllo dei componenti gia' presenti")

        self.ensure_venv()
        self.purge_pip_cache()
        self.report(4, "Ambiente virtuale pronto")

        # Check EVERY component (presence, integrity, minimum version): only what is needed gets installed.
        reqs = requirement_lines(REQUIREMENTS_DIR / "requirements.txt")
        all_reqs = [("torch", "torch"), ("torchvision", "torchvision")] + reqs
        status = ({n: (None, self.MISSING) for n, _ in all_reqs} if force
                  else self.component_status(all_reqs))
        self.show_status(status)
        self.report(6, "Componenti controllati")

        # --- PyTorch (before ultralytics, so pip does not download a different build) ---
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

        # --- libraries: missing/old ones are installed, damaged ones are reinstalled ---
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

        # --- indirect dependencies ---
        self.fix_dependencies()

        if not self.dry:
            self.report(98, "Verifica finale")
            bad = self.failing_imports()
            if bad and any("numpy" in e.lower() for e in bad.values()):
                say("[..] Incompatibilita' con NumPy: provo con una versione compatibile ...")
                self.pip("install", "--force-reinstall", "--no-deps", "numpy<2.3", check=False)
                bad = self.failing_imports()
            if bad:
                raise RuntimeError("verifica finale fallita, moduli non importabili: "
                                   + "; ".join(f"{m} ({e})" for m, e in bad.items()))
            state.mark_component("core", os=self.os_name, torch=choice.label,
                                 python=".".join(map(str, self.info.python)),
                                 gpu_unsupported=bool(plan.training_torch_candidates(self.info))
                                 and not choice.label.startswith("cu")
                                 and not self.skipped_space and not self.disk_full and not self.gpu_declined,
                                 gpu_declined=self.gpu_declined)
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
        if self.prefetch:
            if variant.startswith("cu") and self.cuda_works():
                say("[OK] PyTorch con GPU gia' presente: nulla da scaricare.")
                self.report(100, "Nulla da scaricare")
                return
            cand = plan.training_torch_candidates(self.info)[0]
            say(f"[..] Scarico PyTorch con supporto GPU ({cand.label}) senza installarlo ancora ...")
            rc = self.fast_install(("install", "--force-reinstall", "torch", "torchvision",
                                    "--index-url", cand.index_url), (0, 100), download_only=True)
            if rc != 0:
                raise RuntimeError("download dei componenti non riuscito: controlla la connessione e riprova")
            self.report(100, "Download completato")
            return
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

        extra = requirement_lines(REQUIREMENTS_DIR / "requirements-training.txt")
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


# ---- utilities for restarting the app (installation launched from the GUI) ---
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
    """Best-effort notification (useful when the installation runs without a window)."""
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
    ap.add_argument("--repair", action="store_true",
                    help="controlla i file del venv e reinstalla solo i pacchetti danneggiati")
    ap.add_argument("--deep", action="store_true", help="con --repair: verifica anche l'SHA-256 di ogni file (lento)")
    ap.add_argument("--force", action="store_true", help="reinstalla anche se risulta gia' tutto a posto")
    ap.add_argument("--dry-run", action="store_true", help="mostra i comandi senza eseguirli")
    ap.add_argument("--wait-pid", type=int, default=0, help="attende la chiusura di questo processo (app)")
    ap.add_argument("--relaunch", action="store_true", help="riavvia l'app al termine")
    ap.add_argument("--cpu-only", action="store_true", help="non installare PyTorch con supporto GPU")
    ap.add_argument("--prefetch", action="store_true", help="solo download dei componenti di training (senza installare)")
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

    inst = Installer(os_name, a.dry_run, a.progress, a.cpu_only, a.prefetch)

    # If we are not already in the project venv, we create it and relaunch the installer there.
    in_venv = Path(sys.prefix).resolve() == state.venv_dir(os_name).resolve()
    rc = 0
    try:
        if a.wait_pid:
            say("[..] Attendo la chiusura dell'applicativo ...")
            wait_for_exit(a.wait_pid)
        if a.repair:
            rc = 0 if inst.repair(a.deep) else 1
        elif a.component == "core" and not in_venv and not a.dry_run:
            inst.ensure_venv()
            args = [str(inst.vpy), "-m", "common.ambient.installer", "--os", os_name, "--component", "core", "--yes"]
            args += ["--force"] if a.force else []
            args += ["--progress"] if a.progress else []
            args += ["--cpu-only"] if a.cpu_only else []
            return subprocess.call(args, cwd=str(ROOT))
        elif a.component == "core":
            inst.install_core(a.force)
        else:
            legacy = (state.venv_dir(os_name) / ".setup_complete").exists()  # earlier installations
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
    if a.relaunch and not a.dry_run and (rc == 0 or not a.repair):   # never reopen an app that is still broken
        relaunch_app(os_name)
    return rc
