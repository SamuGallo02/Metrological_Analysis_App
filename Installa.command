:<<"::CMDLITERAL"
@echo off
rem ===========================================================================
rem  INSTALLER - Analisi Metrologica  (un solo file per Windows, macOS e Linux)
rem ===========================================================================
rem  Controlla se c'e' un Python adatto (con tkinter) e, solo se manca, lo installa;
rem  poi apre la finestra di installazione (scelta della cartella, barra di
rem  avanzamento, collegamento sul Desktop). Il codice e' incluso in fondo a questo
rem  file. Indirizzo da cui l'installer scarica l'applicativo: SOURCE_URL in cima
rem  alla parte Python (oggi GitHub; per passare a un server basta cambiarlo).
rem
rem  File generato da distribution/build_installer.py: NON modificarlo a mano.
rem  WINDOWS : doppio clic.   macOS : doppio clic su Installa.command.
rem  Linux   : sh Installa.cmd
rem ===========================================================================
if not "%~1"=="_min" start "" /min cmd /c ""%~f0" _min" & exit /b
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "$t=[IO.File]::ReadAllText('%~f0'); $i=$t.IndexOf('#PS_'+'BEGIN'); $j=$t.IndexOf('::CMD'+'LITERAL',$i); Invoke-Expression $t.Substring($i,$j-$i)"
exit /b %ERRORLEVEL%

#PS_BEGIN
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationFramework
$PyVersion = '3.12.6'

function Test-Py($exe) {
    # Python >= 3.10 con tkinter funzionante
    try {
        & $exe -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function Find-Python {
    $cands = @()
    foreach ($d in ($env:PATH -split ';')) {
        if ($d -and $d -notmatch 'WindowsApps') { $cands += (Join-Path $d 'python.exe') }
    }
    $base = Join-Path $env:LocalAppData 'Programs\Python'
    if (Test-Path $base) {
        Get-ChildItem $base -Directory -Filter 'Python*' | ForEach-Object { $cands += (Join-Path $_.FullName 'python.exe') }
    }
    foreach ($c in $cands) {
        if ((Test-Path $c) -and (Test-Py $c)) { return $c }
    }
    return $null
}

try {
    $py = Find-Python
    if (-not $py) {
        [void][Windows.MessageBox]::Show("Non e' stato trovato Python 3.10 o successivo.`nVerra' scaricato e installato Python $PyVersion (solo per l'utente corrente, senza diritti di amministratore).`n`nPremi OK: comparira' la finestra di installazione di Python.", 'Analisi Metrologica', 'OK', 'Information')
        $inst = Join-Path $env:TEMP "python-$PyVersion-amd64.exe"
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-amd64.exe" -OutFile $inst -UseBasicParsing
        Start-Process -FilePath $inst -ArgumentList '/passive','InstallAllUsers=0','PrependPath=1','Include_launcher=0','Include_test=0','Include_tcltk=1' -Wait
        Remove-Item $inst -Force -ErrorAction SilentlyContinue
        $py = Find-Python
        if (-not $py) { throw 'Installazione automatica di Python non riuscita.' }
    }

    # Estrae la finestra di installazione (incorporata in fondo a questo file) e la avvia senza console
    $k  = $t.LastIndexOf('##PYSRC_' + 'BEGIN')
    $nl = $t.IndexOf("`n", $k)
    $gui = Join-Path $env:TEMP 'am_installer_gui.py'
    [IO.File]::WriteAllText($gui, $t.Substring($nl + 1), (New-Object Text.UTF8Encoding $false))
    $pyw = Join-Path (Split-Path $py) 'pythonw.exe'
    Start-Process -FilePath $pyw -ArgumentList ('"' + $gui + '"')
    exit 0
} catch {
    [void][Windows.MessageBox]::Show("Impossibile avviare l'installazione:`n$($_.Exception.Message)", 'Analisi Metrologica', 'OK', 'Error')
    exit 1
}
::CMDLITERAL

# ============================== macOS / Linux ===============================
case "$(uname -s)" in
    Darwin) AM_OS=macos ;;
    Linux)  AM_OS=linux ;;
    *) echo "Sistema non supportato: $(uname -s)"; exit 1 ;;
esac
PY_VERSION="3.12.6"

echo "Analisi Metrologica - preparazione dell'installer ($AM_OS)..."

# Python >= 3.10 con tkinter (per la finestra); in mancanza si ripiega sulla modalita' testuale
py_ok()  { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; }
tk_ok()  { "$1" -c 'import tkinter' >/dev/null 2>&1; }
venv_ok(){ "$1" -c 'import venv, ensurepip' >/dev/null 2>&1; }

find_python() {   # $1 = "tk" per pretendere tkinter
    for cand in python3.13 python3.12 python3.11 python3.10 python3; do
        p="$(command -v "$cand" 2>/dev/null)"
        [ -n "$p" ] || continue
        [ "$AM_OS" = macos ] && [ "$p" = "/usr/bin/python3" ] && continue   # stub di Xcode
        py_ok "$p" && venv_ok "$p" || continue
        if [ "$1" = tk ]; then tk_ok "$p" || continue; fi
        echo "$p"; return 0
    done
    if [ "$AM_OS" = macos ]; then
        for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/3.*/bin/python3; do
            [ -x "$p" ] && py_ok "$p" || continue
            if [ "$1" = tk ]; then tk_ok "$p" || continue; fi
            echo "$p"; return 0
        done
    fi
    return 1
}

install_python() {
    echo "Installo Python 3 (potrebbe chiedere la password)..."
    if [ "$AM_OS" = macos ]; then
        if command -v brew >/dev/null 2>&1; then
            brew install python@3.12 python-tk@3.12 || return 1
        else
            pkg="/tmp/python-$PY_VERSION.pkg"
            curl -fsSL -o "$pkg" "https://www.python.org/ftp/python/$PY_VERSION/python-$PY_VERSION-macos11.pkg" || return 1
            sudo installer -pkg "$pkg" -target / || return 1
            rm -f "$pkg"
        fi
    else
        if   command -v apt-get >/dev/null 2>&1; then sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip python3-tk
        elif command -v dnf     >/dev/null 2>&1; then sudo dnf install -y python3 python3-pip python3-tkinter
        elif command -v pacman  >/dev/null 2>&1; then sudo pacman -S --noconfirm python python-pip tk
        elif command -v zypper  >/dev/null 2>&1; then sudo zypper install -y python3 python3-pip python3-tk
        else echo "Gestore pacchetti non riconosciuto: installa a mano Python 3.10+ (con venv e tkinter)."; return 1
        fi
    fi
}

install_tk() {
    echo "Installo il supporto grafico (tkinter)..."
    if [ "$AM_OS" = macos ]; then
        command -v brew >/dev/null 2>&1 && brew install python-tk@3.12
    elif command -v apt-get >/dev/null 2>&1; then sudo apt-get install -y python3-tk
    elif command -v dnf     >/dev/null 2>&1; then sudo dnf install -y python3-tkinter
    elif command -v pacman  >/dev/null 2>&1; then sudo pacman -S --noconfirm tk
    elif command -v zypper  >/dev/null 2>&1; then sudo zypper install -y python3-tk
    fi
}

PY="$(find_python tk)"
if [ -z "$PY" ]; then
    PY="$(find_python)"                      # c'e' un Python ma senza tkinter?
    if [ -z "$PY" ]; then
        install_python || { echo "[ERRORE] Installazione di Python non riuscita."; exit 1; }
    else
        install_tk
    fi
    PY="$(find_python tk)"
    [ -z "$PY" ] && PY="$(find_python)"      # senza tkinter: modalita' testuale
    [ -z "$PY" ] && { echo "[ERRORE] Python 3.10+ non disponibile: apri un nuovo terminale e riesegui."; exit 1; }
fi

GUI="$(mktemp -d)/am_installer_gui.py"
sed -n '/^##PYSRC_BEGIN$/,$p' "$0" | tail -n +2 > "$GUI"
[ -s "$GUI" ] || { echo "[ERRORE] Il file installer e' incompleto: scaricalo di nuovo."; exit 1; }

if tk_ok "$PY"; then
    nohup "$PY" "$GUI" $AM_GUI_ARGS >/dev/null 2>&1 &
    echo "Finestra di installazione avviata."
else
    echo "tkinter non disponibile: installazione in modalita' testuale."
    "$PY" "$GUI" --cli $AM_GUI_ARGS
fi
exit 0
##PYSRC_BEGIN
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Installer grafico - Analisi Metrologica (Windows, macOS, Linux)
================================================================
Unico file da distribuire. Mostra una finestra (niente terminale) in cui l'utente
sceglie il sistema operativo e la cartella di installazione; poi:
  1. scarica il codice dell'applicativo dall'indirizzo SOURCE_URL (oggi GitHub,
     in futuro un sito/server: basta cambiare quella costante o impostare la
     variabile d'ambiente AM_SOURCE_URL);
  2. installa solo cio' che manca (ambiente virtuale, PyTorch nella build adatta
     all'hardware, librerie) tramite il pacchetto installer/ del progetto;
  3. crea un collegamento sul Desktop.
La barra di avanzamento rappresenta l'intera installazione (0-100%).

Solo libreria standard (tkinter incluso). Se tkinter non c'e' si usa la modalita'
testuale:  python installer_gui.py --cli [--dest CARTELLA]

Autore: Samuele Gallo
"""

from __future__ import annotations

import argparse
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

APP_TITLE = "Analisi Metrologica - Installazione"
APP_NAME = "Analisi Metrologica"
SOURCE_URL = os.environ.get(
    "AM_SOURCE_URL",
    "https://github.com/SamuGallo02/Metrological_Analysis_App/archive/refs/heads/main.zip",
)
MIN_PY = (3, 10)
OS_LABELS = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}
NOWIN = {"creationflags": 0x08000000} if os.name == "nt" else {}  # niente console su Windows


FROZEN = bool(getattr(sys, "frozen", False))   # True nell'.exe/.app creato con PyInstaller
PY_VERSION = "3.12.6"
DEVNULL_IN = {"stdin": subprocess.DEVNULL}     # evita errori di handle quando non c'e' console


def detect_os() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    return "macos" if sys.platform == "darwin" else "linux"


def default_dest() -> Path:
    return Path.home() / "Analisi_Metrologica"


def console_python() -> str:
    """Interprete con cui lanciare i sottoprocessi (su Windows python.exe, non pythonw.exe)."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        cand = exe.with_name("python.exe")
        if cand.exists():
            return str(cand)
    return str(exe)


def _py_ok(exe: str) -> bool:
    """Python >= 3.10 capace di creare ambienti virtuali."""
    try:
        r = subprocess.run([exe, "-c", "import sys, venv, ensurepip; sys.exit(0 if sys.version_info >= (3, 10) else 1)"],
                           capture_output=True, timeout=60, **DEVNULL_IN, **NOWIN)
        return r.returncode == 0
    except Exception:
        return False


def find_system_python() -> Optional[str]:
    """Cerca un Python adatto gia' installato (solo per l'.exe/.app, che non ne ha uno proprio)."""
    cands: list = []
    os_name = detect_os()
    if os_name == "windows":
        for d in os.environ.get("PATH", "").split(os.pathsep):
            if d and "windowsapps" not in d.lower():
                cands.append(os.path.join(d, "python.exe"))
        for base in (os.environ.get("LOCALAPPDATA", "") + r"\Programs\Python",
                     os.environ.get("ProgramFiles", r"C:\Program Files"), "C:\\"):
            if os.path.isdir(base):
                for sub in sorted(Path(base).glob("Python3*"), reverse=True):
                    cands.append(str(sub / "python.exe"))
    else:
        for name in ("python3.13", "python3.12", "python3.11", "python3.10", "python3"):
            w = shutil.which(name)
            if w and w != "/usr/bin/python3":          # stub di Xcode su macOS
                cands.append(w)
        cands += ["/opt/homebrew/bin/python3", "/usr/local/bin/python3"]
        cands += sorted(map(str, Path("/Library/Frameworks/Python.framework/Versions").glob("3.*/bin/python3")), reverse=True)
    seen = set()
    for c in cands:
        if c in seen or not os.path.isfile(c):
            continue
        seen.add(c)
        if _py_ok(c):
            return c
    return None


def has_nvidia() -> bool:
    return shutil.which("nvidia-smi") is not None or (
        os.name == "nt" and Path(r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe").exists())


def venv_python_path(dest: Path, os_name: str) -> Path:
    v = {"windows": "venv", "macos": "venv_mac", "linux": "venv_linux"}[os_name]
    return dest / v / ("Scripts/pythonw.exe" if os_name == "windows" else "bin/python")


# --------------------------------------------------------------------------- #
#  Pipeline (indipendente dall'interfaccia)
# --------------------------------------------------------------------------- #
class Cancelled(Exception):
    pass


class Pipeline:
    """emit(percentuale, testo) aggiorna la barra; log(riga) alimenta i dettagli."""

    def __init__(self, dest: Path, os_name: str, shortcut: bool, update_code: bool,
                 emit: Callable[[float, str], None], log: Callable[[str], None]):
        self.dest, self.os_name = dest, os_name
        self.shortcut, self.update_code = shortcut, update_code
        self.emit, self.log = emit, log
        self.proc: Optional[subprocess.Popen] = None
        self.python: Optional[str] = None
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    def _check(self) -> None:
        if self.cancelled:
            raise Cancelled()

    # -- download generico con avanzamento -------------------------------------
    def _download(self, url: str, dest_file: Path, lo: float, hi: float, label: str) -> None:
        req = urllib.request.Request(url, headers={"User-Agent": "AnalisiMetrologica-Installer"})
        with urllib.request.urlopen(req, timeout=60) as r, open(dest_file, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            got, t0 = 0, time.time()
            while True:
                self._check()
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if total:
                    self.emit(lo + (hi - lo) * got / total, f"{label} ({got // (1024 * 1024)} MB)")
                else:  # dimensione ignota: avanzamento a tempo
                    self.emit(lo + (hi - lo) * (1 - 0.5 ** ((time.time() - t0) / 3)), label)

    def _wait_creep(self, proc: subprocess.Popen, lo: float, hi: float, label: str, tau: float = 40.0) -> int:
        t0 = time.time()
        while proc.poll() is None:
            self._check()
            self.emit(lo + (hi - lo) * (1 - 0.5 ** ((time.time() - t0) / tau)), label)
            time.sleep(0.5)
        return proc.returncode

    # -- 0. Python (solo .exe/.app: da script si usa quello che sta eseguendo l'installer) --
    def ensure_python(self) -> None:
        if not FROZEN:
            self.python = console_python()
            return
        self.emit(1, "Cerco Python sul computer...")
        self.python = find_system_python()
        if self.python:
            self.log(f"Python gia' presente: {self.python}")
            self.emit(12, "Python gia' presente")
            return
        tmpdir = Path(os.environ.get("TMPDIR") or os.environ.get("TEMP") or "/tmp")
        if self.os_name == "windows":
            inst = tmpdir / f"python-{PY_VERSION}-amd64.exe"
            self._download(f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-amd64.exe",
                           inst, 1, 8, "Scarico Python")
            self.emit(8, "Installo Python...")
            proc = subprocess.Popen([str(inst), "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_launcher=0",
                                     "Include_test=0", "Include_tcltk=0"], **DEVNULL_IN, **NOWIN)
            rc = self._wait_creep(proc, 8, 12, "Installo Python...", 25)
            if rc != 0:
                raise RuntimeError(f"Installazione di Python non riuscita (codice {rc}).")
        elif self.os_name == "macos":
            inst = tmpdir / f"python-{PY_VERSION}.pkg"
            self._download(f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-macos11.pkg",
                           inst, 1, 8, "Scarico Python")
            self.emit(8, "Installo Python (macOS chiedera' la password)...")
            script = f'do shell script "installer -pkg \\"{inst}\\" -target /" with administrator privileges'
            proc = subprocess.Popen(["osascript", "-e", script], **DEVNULL_IN)
            rc = self._wait_creep(proc, 8, 12, "Installo Python...", 25)
            if rc != 0:
                raise RuntimeError("Installazione di Python non riuscita o annullata.")
        else:
            raise RuntimeError("Python 3.10+ non trovato: installalo con il gestore pacchetti.")
        try:
            inst.unlink()
        except OSError:
            pass
        self.python = find_system_python()
        if not self.python:
            raise RuntimeError("Python installato ma non trovato: riavvia l'installer.")
        self.emit(12, "Python pronto")

    # -- 1. codice ------------------------------------------------------------
    def have_code(self) -> bool:
        return (self.dest / "main.py").exists() and (self.dest / "installer" / "__init__.py").exists()

    def download_code(self) -> None:
        self.emit(12, "Scarico il codice dell'applicativo...")
        self.log(f"Sorgente: {SOURCE_URL}")
        tmp = Path(os.environ.get("TMPDIR") or os.environ.get("TEMP") or "/tmp") / "am_source.zip"
        self._download(SOURCE_URL, tmp, 12, 19, "Scarico il codice")
        self.emit(19, "Estraggo i file...")
        self.dest.mkdir(parents=True, exist_ok=True)
        base = os.path.realpath(str(self.dest))
        with zipfile.ZipFile(tmp) as z:
            names = [n for n in z.namelist() if n and not n.startswith("__MACOSX")]
            tops = {n.split("/", 1)[0] for n in names}
            strip = (next(iter(tops)) + "/") if len(tops) == 1 and any("/" in n for n in names) else ""
            for info in z.infolist():
                name = info.filename
                if name.startswith("__MACOSX") or not name.startswith(strip) or name == strip:
                    continue
                target = os.path.realpath(os.path.join(base, name[len(strip):]))
                if not target.startswith(base + os.sep):
                    continue  # difesa da percorsi malevoli nello zip
                if info.is_dir():
                    os.makedirs(target, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with z.open(info) as src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out)
                    if (info.external_attr >> 16) & 0o111:
                        os.chmod(target, 0o755)
        try:
            tmp.unlink()
        except OSError:
            pass
        if not self.have_code():
            raise RuntimeError("Il sorgente scaricato non contiene l'applicativo completo "
                               "(manca main.py o la cartella installer/).")
        self.emit(20, "Codice installato")

    # -- 2. componenti (pacchetto installer/ del progetto) ---------------------
    def run_components(self) -> None:
        cmd = [self.python, "-m", "installer", "--os", self.os_name,
               "--component", "core", "--yes", "--progress"]
        self.log("> " + " ".join(cmd))
        self.proc = subprocess.Popen(cmd, cwd=str(self.dest), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace", **DEVNULL_IN, **NOWIN)
        for line in self.proc.stdout:
            line = line.rstrip()
            if line.startswith("@@PROGRESS"):
                parts = line.split(" ", 2)
                try:
                    pct = float(parts[1])
                except (IndexError, ValueError):
                    continue
                self.emit(20 + pct * 0.75, parts[2] if len(parts) > 2 and parts[2] else "")
            elif line:
                self.log(line)
        rc = self.proc.wait()
        self._check()
        if rc != 0:
            raise RuntimeError(f"Installazione dei componenti non riuscita (codice {rc}). "
                               f"Dettagli in {self.dest / 'install_log.txt'}")

    # -- 3. collegamento sul Desktop ------------------------------------------
    def create_shortcut(self) -> None:
        self.emit(96, "Creo il collegamento sul Desktop...")
        try:
            {"windows": self._sc_windows, "macos": self._sc_macos, "linux": self._sc_linux}[self.os_name]()
        except Exception as e:  # il collegamento non e' essenziale
            self.log(f"[ATTENZIONE] Collegamento non creato: {e}")

    def _sc_windows(self) -> None:
        ico = self.dest / "assets" / "app_icon.ico"
        env = dict(os.environ, AM_T=str(venv_python_path(self.dest, "windows")), AM_A='"main.py"',
                   AM_W=str(self.dest), AM_I=str(ico) if ico.exists() else "", AM_N=APP_NAME)
        ps = ("$d=[Environment]::GetFolderPath('Desktop'); "
              "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d ($env:AM_N+'.lnk'))); "
              "$s.TargetPath=$env:AM_T; $s.Arguments=$env:AM_A; $s.WorkingDirectory=$env:AM_W; "
              "if($env:AM_I){$s.IconLocation=$env:AM_I}; $s.Description='Stereo Metrology Analysis'; $s.Save()")
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                       env=env, check=True, timeout=60, **DEVNULL_IN, **NOWIN)

    def _desktop_dir(self) -> Path:
        d = Path.home() / "Desktop"
        return d if d.exists() else Path.home()

    def _sc_macos(self) -> None:
        app = self._desktop_dir() / f"{APP_NAME}.app"
        macos = app / "Contents" / "MacOS"
        macos.mkdir(parents=True, exist_ok=True)
        run = macos / "run"
        run.write_text(f'#!/bin/bash\ncd "{self.dest}"\nexec "{venv_python_path(self.dest, "macos")}" main.py\n')
        run.chmod(0o755)
        (app / "Contents" / "Info.plist").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict>\n'
            f'<key>CFBundleName</key><string>{APP_NAME}</string>\n'
            '<key>CFBundleExecutable</key><string>run</string>\n'
            '<key>CFBundleIdentifier</key><string>it.unipd.stereometrology</string>\n'
            '<key>CFBundlePackageType</key><string>APPL</string>\n'
            '<key>NSCameraUsageDescription</key><string>Serve per la demo con webcam.</string>\n'
            '</dict></plist>\n')

    def _sc_linux(self) -> None:
        png = next(iter((self.dest / "assets").glob("*.png")), None) if (self.dest / "assets").exists() else None
        text = ("[Desktop Entry]\nType=Application\nName=" + APP_NAME + "\n"
                f"Exec={venv_python_path(self.dest, 'linux')} {self.dest / 'main.py'}\n"
                f"Path={self.dest}\nTerminal=false\nCategories=Science;\n" + (f"Icon={png}\n" if png else ""))
        for d in (self._desktop_dir(), Path.home() / ".local" / "share" / "applications"):
            d.mkdir(parents=True, exist_ok=True)
            f = d / "analisi-metrologica.desktop"
            f.write_text(text)
            f.chmod(0o755)

    # -- esecuzione -----------------------------------------------------------
    def run(self) -> None:
        self.emit(1, "Controllo cio' che e' gia' presente...")
        self.ensure_python()
        self._check()
        if self.have_code() and not self.update_code:
            self.log("Codice gia' presente: salto il download.")
            self.emit(20, "Codice gia' presente")
        else:
            self.download_code()
        self._check()
        self.run_components()
        self._check()
        if self.shortcut:
            self.create_shortcut()
        self.emit(100, "Installazione completata")

    def launch(self) -> None:
        py = venv_python_path(self.dest, self.os_name)
        kw = {"creationflags": 0x00000008 | 0x00000200} if os.name == "nt" else {"start_new_session": True}
        subprocess.Popen([str(py), str(self.dest / "main.py")], cwd=str(self.dest),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kw)


# --------------------------------------------------------------------------- #
#  Interfaccia grafica
# --------------------------------------------------------------------------- #
def run_gui(initial_dest: Optional[Path]) -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("560x420")
    root.minsize(520, 380)
    detected = detect_os()
    ui_q: "queue.Queue" = queue.Queue()
    state = {"pipe": None, "running": False}

    outer = ttk.Frame(root, padding=18)
    outer.pack(fill="both", expand=True)

    # ---------- schermata 1: scelte ----------
    setup = ttk.Frame(outer)
    ttk.Label(setup, text=APP_NAME, font=("TkDefaultFont", 16, "bold")).pack(anchor="w")
    ttk.Label(setup, text="Verranno installati solo i componenti che mancano e che servono "
                          "a questo computer.", wraplength=500).pack(anchor="w", pady=(2, 12))

    row = ttk.Frame(setup)
    row.pack(fill="x", pady=4)
    ttk.Label(row, text="Sistema operativo:", width=20).pack(side="left")
    os_var = tk.StringVar(value=OS_LABELS[detected])
    os_box = ttk.Combobox(row, textvariable=os_var, values=list(OS_LABELS.values()), state="readonly", width=14)
    os_box.pack(side="left")
    os_warn = ttk.Label(setup, text="", foreground="#b00020", wraplength=500)
    os_warn.pack(anchor="w")

    row = ttk.Frame(setup)
    row.pack(fill="x", pady=4)
    ttk.Label(row, text="Cartella di installazione:", width=20).pack(side="left")
    dest_var = tk.StringVar(value=str(initial_dest or default_dest()))
    ttk.Entry(row, textvariable=dest_var).pack(side="left", fill="x", expand=True)

    def browse() -> None:
        sel = filedialog.askdirectory(title="Scegli la cartella di installazione",
                                      initialdir=str(Path(dest_var.get()).parent))
        if not sel:
            return
        p = Path(sel)
        try:
            if p.exists() and any(p.iterdir()) and not (p / "main.py").exists():
                p = p / "Analisi_Metrologica"   # cartella non vuota: usa una sottocartella
        except OSError:
            pass
        dest_var.set(str(p))

    ttk.Button(row, text="Sfoglia...", command=browse).pack(side="left", padx=(6, 0))

    shortcut_var = tk.BooleanVar(value=True)
    update_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(setup, text="Crea un collegamento sul Desktop", variable=shortcut_var).pack(anchor="w", pady=(10, 0))
    ttk.Checkbutton(setup, text="Riscarica il codice anche se e' gia' presente (aggiornamento)",
                    variable=update_var).pack(anchor="w")

    gpu_txt = ("GPU NVIDIA rilevata: verra' installato PyTorch con supporto GPU (download di alcuni GB)."
               if has_nvidia() and detected != "macos" else
               "Spazio e download: circa 1-2 GB." if detected != "macos" else
               "Mac: PyTorch con accelerazione Apple GPU (MPS) inclusa.")
    ttk.Label(setup, text=gpu_txt, foreground="#555555", wraplength=500).pack(anchor="w", pady=(12, 0))

    btns = ttk.Frame(setup)
    btns.pack(side="bottom", fill="x", pady=(18, 0))
    install_btn = ttk.Button(btns, text="Installa")
    install_btn.pack(side="right")
    ttk.Button(btns, text="Esci", command=root.destroy).pack(side="right", padx=8)
    setup.pack(fill="both", expand=True)

    def check_os(*_):
        chosen = next(k for k, v in OS_LABELS.items() if v == os_var.get())
        if chosen != detected:
            os_warn.config(text=f"Questo computer e' {OS_LABELS[detected]}: scegli {OS_LABELS[detected]}, "
                                f"oppure esegui l'installer sul computer {OS_LABELS[chosen]}.")
            install_btn.state(["disabled"])
        else:
            os_warn.config(text="")
            install_btn.state(["!disabled"])

    os_box.bind("<<ComboboxSelected>>", check_os)
    check_os()

    # ---------- schermata 2: avanzamento ----------
    prog = ttk.Frame(outer)
    ttk.Label(prog, text="Installazione in corso", font=("TkDefaultFont", 14, "bold")).pack(anchor="w")
    status_var = tk.StringVar(value="Preparazione...")
    ttk.Label(prog, textvariable=status_var, wraplength=500).pack(anchor="w", pady=(8, 4))
    bar = ttk.Progressbar(prog, maximum=100, mode="determinate")
    bar.pack(fill="x")
    pct_var = tk.StringVar(value="0%")
    ttk.Label(prog, textvariable=pct_var).pack(anchor="e")
    ttk.Label(prog, text="Non chiudere questa finestra: con una GPU NVIDIA il download puo' richiedere "
                         "diversi minuti.", foreground="#555555", wraplength=500).pack(anchor="w", pady=(6, 0))

    details_open = tk.BooleanVar(value=False)
    log_frame = ttk.Frame(prog)
    log_text = tk.Text(log_frame, height=9, wrap="none", state="disabled", font=("TkFixedFont", 8))
    sb = ttk.Scrollbar(log_frame, command=log_text.yview)
    log_text.config(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    log_text.pack(side="left", fill="both", expand=True)

    def toggle_details() -> None:
        if details_open.get():
            log_frame.pack(fill="both", expand=True, pady=(8, 0))
        else:
            log_frame.pack_forget()

    ttk.Checkbutton(prog, text="Mostra dettagli", variable=details_open, command=toggle_details).pack(anchor="w", pady=(10, 0))

    pbtns = ttk.Frame(prog)
    pbtns.pack(side="bottom", fill="x", pady=(10, 0))
    cancel_btn = ttk.Button(pbtns, text="Annulla")
    cancel_btn.pack(side="right")
    launch_btn = ttk.Button(pbtns, text="Avvia l'applicazione")
    close_btn = ttk.Button(pbtns, text="Chiudi", command=root.destroy)

    # ---------- logica ----------
    def append_log(line: str) -> None:
        log_text.config(state="normal")
        log_text.insert("end", line + "\n")
        log_text.see("end")
        log_text.config(state="disabled")

    def pump() -> None:
        try:
            while True:
                kind, a, b = ui_q.get_nowait()
                if kind == "p":
                    bar["value"] = a
                    pct_var.set(f"{int(a)}%")
                    if b:
                        status_var.set(b)
                elif kind == "l":
                    append_log(a)
                elif kind == "done":
                    finish(a, b)
        except queue.Empty:
            pass
        root.after(100, pump)

    def finish(ok: bool, err: str) -> None:
        state["running"] = False
        cancel_btn.pack_forget()
        if ok:
            bar["value"] = 100
            pct_var.set("100%")
            status_var.set("Installazione completata.")
            launch_btn.pack(side="right")
            close_btn.pack(side="right", padx=8)
        else:
            status_var.set(f"Installazione non riuscita: {err}")
            details_open.set(True)
            toggle_details()
            close_btn.pack(side="right")

    def start() -> None:
        dest = Path(dest_var.get()).expanduser()
        try:
            dest.mkdir(parents=True, exist_ok=True)
            if not os.access(dest, os.W_OK):
                raise PermissionError(dest)
        except OSError as e:
            messagebox.showerror(APP_TITLE, f"Impossibile usare la cartella scelta:\n{e}")
            return
        if not FROZEN and sys.version_info < MIN_PY:
            messagebox.showerror(APP_TITLE, "Serve Python 3.10 o successivo.")
            return
        setup.pack_forget()
        prog.pack(fill="both", expand=True)
        pipe = Pipeline(dest, detected, shortcut_var.get(), update_var.get(),
                        emit=lambda p, t: ui_q.put(("p", p, t)),
                        log=lambda l: ui_q.put(("l", l, "")))
        state["pipe"], state["running"] = pipe, True

        def work() -> None:
            try:
                pipe.run()
                ui_q.put(("done", True, ""))
            except Cancelled:
                ui_q.put(("done", False, "annullata dall'utente"))
            except Exception as e:
                ui_q.put(("l", f"[ERRORE] {e}", ""))
                ui_q.put(("done", False, str(e)))

        threading.Thread(target=work, daemon=True).start()

    def cancel() -> None:
        if state["pipe"] and messagebox.askyesno(APP_TITLE, "Interrompere l'installazione?"):
            state["pipe"].cancel()

    def on_close() -> None:
        if state["running"]:
            cancel()
        else:
            root.destroy()

    def launch() -> None:
        state["pipe"].launch()
        root.destroy()

    install_btn.config(command=start)
    cancel_btn.config(command=cancel)
    launch_btn.config(command=launch)
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.after(100, pump)
    root.mainloop()
    return 0


def run_cli(dest: Path, shortcut: bool, update: bool) -> int:
    last = [-1]

    def emit(p: float, t: str) -> None:
        if int(p) != last[0]:
            last[0] = int(p)
            print(f"[{int(p):3d}%] {t}", flush=True)

    pipe = Pipeline(dest, detect_os(), shortcut, update, emit, lambda l: print("   " + l, flush=True))
    try:
        pipe.run()
    except Exception as e:
        print(f"[ERRORE] {e}")
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=APP_TITLE)
    ap.add_argument("--cli", action="store_true", help="modalita' testuale (senza finestra)")
    ap.add_argument("--dest", help="cartella di installazione")
    ap.add_argument("--no-shortcut", action="store_true")
    ap.add_argument("--update", action="store_true", help="riscarica il codice anche se presente")
    a = ap.parse_args()
    dest = Path(a.dest).expanduser() if a.dest else None
    if not a.cli:
        try:
            import tkinter  # noqa: F401
        except ImportError:
            print("tkinter non disponibile: passo alla modalita' testuale.")
            a.cli = True
    if a.cli:
        return run_cli(dest or default_dest(), not a.no_shortcut, a.update)
    return run_gui(dest)


if __name__ == "__main__":
    sys.exit(main())
