#!/bin/bash
# Application launcher (macOS). Installation is done only once with the installer
# downloadable from the website (result in librery/.install_state.json); nothing is checked here.
cd "$(dirname "$0")/../.." || exit 1
VENV_PY="librery/venv_mac/bin/python"

if [ ! -x "$VENV_PY" ] || [ ! -f librery/.install_state.json ]; then
    echo "L'applicativo non e' ancora installato su questo Mac."
    echo "Scarica l'installer da: https://samugallo02.github.io/Nautilus_Website/"
    open "https://samugallo02.github.io/Nautilus_Website/" 2>/dev/null
    exit 1
fi

nohup "$VENV_PY" main.py >/dev/null 2>&1 &
disown
exit 0
