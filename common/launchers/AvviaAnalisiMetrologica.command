#!/bin/bash
# Application launcher (macOS). If the environment is missing, the usual installer is run here to install
# only what is needed (no website, no download of the installer); the app then repairs its own files at startup.
cd "$(dirname "$0")/../.." || exit 1
VENV_PY="librery/venv_mac/bin/python"

# a missing main.py (damaged copy): restore only the missing files
if [ ! -f main.py ] && command -v python3 >/dev/null; then
    python3 -m common.ambient.updater repair
fi

if [ ! -x "$VENV_PY" ]; then
    PY="$(command -v python3)"
    if [ -z "$PY" ]; then
        echo "Python 3.10+ non trovato. Usa l'installer: https://samugallo02.github.io/Nautilus_Website/"
        open "https://samugallo02.github.io/Nautilus_Website/" 2>/dev/null
        exit 1
    fi
    echo "Ambiente mancante: installo solo il necessario..."
    "$PY" -m common.ambient.installer --os macos --component core --yes || { echo "Installazione non riuscita."; exit 1; }
fi

nohup "$VENV_PY" main.py >/dev/null 2>&1 &
disown
exit 0
