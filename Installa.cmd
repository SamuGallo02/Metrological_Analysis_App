:<<"::CMDLITERAL"
@echo off
setlocal
rem ===========================================================================
rem  INSTALLER UNICO - Analisi Metrologica  (stesso file per Windows, macOS, Linux)
rem ===========================================================================
rem  Scarica il codice da Internet, installa Python se manca e prepara l'app con
rem  i soli componenti adatti al computer. Sorgente del codice: vedi AM_SOURCE_URL
rem  qui sotto (e nella parte per macOS/Linux, piu' in basso): per passare da
rem  GitHub a un sito/server basta cambiare quell'indirizzo (uno zip con il progetto).
rem  Si puo' anche sovrascrivere senza modificare il file:  set AM_SOURCE_URL=...
rem
rem  WINDOWS : doppio clic su questo file.
rem  macOS/Linux : curl -fsSL <indirizzo-di-questo-file> | sh
rem                oppure, dopo averlo scaricato:  sh Installa.cmd
rem  Autore: Samuele Gallo
rem ===========================================================================
if "%AM_SOURCE_URL%"=="" set "AM_SOURCE_URL=https://github.com/SamuGallo02/Metrological_Analysis_App/archive/refs/heads/main.zip"
if "%AM_DEST%"=="" set "AM_DEST=%USERPROFILE%\Metrological_Analysis_App"
echo.
echo  ANALISI METROLOGICA - installazione
echo  Sistema rilevato: Windows
echo  Cartella di destinazione: %AM_DEST%
echo  Sorgente: %AM_SOURCE_URL%
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$t=[IO.File]::ReadAllText('%~f0'); $i=$t.IndexOf('#PS_'+'BEGIN'); $j=$t.IndexOf('::CMD'+'LITERAL',$i); Invoke-Expression $t.Substring($i,$j-$i)"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo  Installazione NON riuscita. Dettagli: %AM_DEST%\install_log.txt
pause
exit /b %RC%

#PS_BEGIN
$ErrorActionPreference = 'Stop'
$Url  = $env:AM_SOURCE_URL
$Dest = $env:AM_DEST
$PyVersion = '3.12.6'

function Get-PyVersion($exe) {
    try {
        $o = & $exe --version 2>&1 | Out-String
        if ($o -match 'Python\s+(\d+)\.(\d+)') { return [int]$Matches[1] * 100 + [int]$Matches[2] }
    } catch { }
    return 0
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
        if ((Test-Path $c) -and ((Get-PyVersion $c) -ge 310)) { return $c }
    }
    return $null
}

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    # 1. Python
    $py = Find-Python
    if (-not $py) {
        Write-Host "[..] Python 3.10+ non trovato: scarico e installo Python $PyVersion (solo utente corrente)..."
        $inst = Join-Path $env:TEMP "python-$PyVersion-amd64.exe"
        Invoke-WebRequest -Uri "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-amd64.exe" -OutFile $inst -UseBasicParsing
        Start-Process -FilePath $inst -ArgumentList '/quiet','InstallAllUsers=0','PrependPath=1','Include_launcher=0','Include_test=0' -Wait
        Remove-Item $inst -Force -ErrorAction SilentlyContinue
        $py = Find-Python
        if (-not $py) { throw 'Installazione automatica di Python non riuscita.' }
    }
    Write-Host "[OK] Python: $py"

    # 2. Codice sorgente
    Write-Host "[..] Scarico il codice dell'applicativo..."
    $zip = Join-Path $env:TEMP 'am_source.zip'
    $tmp = Join-Path $env:TEMP 'am_source'
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    Invoke-WebRequest -Uri $Url -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $root = $tmp
    $kids = @(Get-ChildItem $tmp)
    if ($kids.Count -eq 1 -and $kids[0].PSIsContainer) { $root = $kids[0].FullName }
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    Copy-Item -Path (Join-Path $root '*') -Destination $Dest -Recurse -Force
    Remove-Item $zip, $tmp -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "[OK] Codice copiato in $Dest"

    # 3. Ambiente e componenti (scelti in base a Windows + hardware rilevato)
    Set-Location $Dest
    & $py -m installer --os windows --component core --yes
    if ($LASTEXITCODE -ne 0) { throw "installer terminato con codice $LASTEXITCODE" }

    Write-Host ''
    Write-Host '[OK] Installazione completata. Avvio dell''applicazione...'
    Start-Process -FilePath 'wscript.exe' -ArgumentList ('"' + (Join-Path $Dest 'AnalisiMetrologica.vbs') + '"')
    exit 0
} catch {
    Write-Host "[ERRORE] $($_.Exception.Message)"
    exit 1
}
::CMDLITERAL

# ============================== macOS / Linux ===============================
AM_SOURCE_URL="${AM_SOURCE_URL:-https://github.com/SamuGallo02/Metrological_Analysis_App/archive/refs/heads/main.zip}"
AM_DEST="${AM_DEST:-$HOME/Metrological_Analysis_App}"
PY_VERSION="3.12.6"

case "$(uname -s)" in
    Darwin) AM_OS=macos ;;
    Linux)  AM_OS=linux ;;
    *) echo "Sistema non supportato: $(uname -s)"; exit 1 ;;
esac

echo
echo " ANALISI METROLOGICA - installazione"
echo " Sistema rilevato: $AM_OS"
echo " Cartella di destinazione: $AM_DEST"
echo " Sorgente: $AM_SOURCE_URL"
echo

python_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; }
venv_ok()   { "$1" -c 'import venv, ensurepip' >/dev/null 2>&1; }

find_python() {
    for cand in python3.13 python3.12 python3.11 python3.10 python3; do
        p="$(command -v "$cand" 2>/dev/null)"
        # su macOS /usr/bin/python3 e' lo stub di Xcode: lo saltiamo
        if [ -n "$p" ] && { [ "$p" != "/usr/bin/python3" ] || [ "$AM_OS" = linux ]; } && python_ok "$p" && venv_ok "$p"; then
            echo "$p"; return 0
        fi
    done
    if [ "$AM_OS" = macos ]; then
        for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/3.*/bin/python3; do
            if [ -x "$p" ] && python_ok "$p"; then echo "$p"; return 0; fi
        done
    fi
    return 1
}

install_python() {
    echo "[..] Python 3.10+ non trovato: lo installo (potrebbe chiedere la password)."
    if [ "$AM_OS" = macos ]; then
        if command -v brew >/dev/null 2>&1; then
            brew install python@3.12 || return 1
        else
            pkg="/tmp/python-$PY_VERSION.pkg"
            curl -L --fail -o "$pkg" "https://www.python.org/ftp/python/$PY_VERSION/python-$PY_VERSION-macos11.pkg" || return 1
            sudo installer -pkg "$pkg" -target / || return 1
            rm -f "$pkg"
        fi
    else
        if   command -v apt-get >/dev/null 2>&1; then sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
        elif command -v dnf     >/dev/null 2>&1; then sudo dnf install -y python3 python3-pip
        elif command -v pacman  >/dev/null 2>&1; then sudo pacman -S --noconfirm python python-pip
        elif command -v zypper  >/dev/null 2>&1; then sudo zypper install -y python3 python3-pip
        else echo "Gestore pacchetti non riconosciuto: installa a mano Python 3.10+ (con venv)."; return 1
        fi
    fi
}

command -v curl >/dev/null 2>&1 || { echo "ERRORE: serve 'curl'."; exit 1; }

SYS_PY="$(find_python)"
if [ -z "$SYS_PY" ]; then
    install_python || { echo "[ERRORE] Installazione di Python non riuscita."; exit 1; }
    SYS_PY="$(find_python)"
    [ -z "$SYS_PY" ] && { echo "[ERRORE] Python installato ma non trovato: apri un nuovo terminale e riesegui."; exit 1; }
fi
echo "[OK] Python: $SYS_PY"

echo "[..] Scarico il codice dell'applicativo..."
TMPD="$(mktemp -d)"
curl -fsSL -o "$TMPD/src.zip" "$AM_SOURCE_URL" || { echo "[ERRORE] Download non riuscito."; rm -rf "$TMPD"; exit 1; }
mkdir -p "$AM_DEST"
"$SYS_PY" -I - "$TMPD/src.zip" "$AM_DEST" <<'PYEOF' || { echo "[ERRORE] Estrazione non riuscita."; rm -rf "$TMPD"; exit 1; }
import os, sys, zipfile
zpath, dest = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(zpath) as z:
    names = [n for n in z.namelist() if n and not n.startswith("__MACOSX")]
    tops = {n.split("/", 1)[0] for n in names}
    # se lo zip ha un'unica cartella radice (come quelli di GitHub) la togliamo
    strip = (next(iter(tops)) + "/") if len(tops) == 1 and any("/" in n for n in names) else ""
    for info in z.infolist():
        name = info.filename
        if name.startswith("__MACOSX") or not name.startswith(strip):
            continue
        rel = name[len(strip):]
        if not rel:
            continue
        target = os.path.realpath(os.path.join(dest, rel))
        if not target.startswith(os.path.realpath(dest) + os.sep):
            continue  # protezione da percorsi malevoli nello zip
        if info.is_dir():
            os.makedirs(target, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                out.write(src.read())
            if (info.external_attr >> 16) & 0o111:
                os.chmod(target, 0o755)
PYEOF
rm -rf "$TMPD"
echo "[OK] Codice copiato in $AM_DEST"

cd "$AM_DEST" || exit 1
chmod +x ./*.command ./*.sh 2>/dev/null
[ "$AM_OS" = macos ] && xattr -dr com.apple.quarantine "$AM_DEST" 2>/dev/null
"$SYS_PY" -m installer --os "$AM_OS" --component core --yes || {
    echo; echo "[ERRORE] Installazione non riuscita. Dettagli: $AM_DEST/install_log.txt"; exit 1; }

echo
echo "[OK] Installazione completata."
if [ "$AM_OS" = macos ]; then
    nohup "$AM_DEST/venv_mac/bin/python" "$AM_DEST/main.py" >/dev/null 2>&1 &
else
    nohup "$AM_DEST/venv_linux/bin/python" "$AM_DEST/main.py" >/dev/null 2>&1 &
fi
exit 0
