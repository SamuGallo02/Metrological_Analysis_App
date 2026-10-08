#!/bin/bash
# Avvio dell'applicativo (macOS). L'installazione si fa una volta sola con l'installer
# scaricabile dal sito (esito in .install_state.json); qui non si controlla nulla.
cd "$(dirname "$0")/.." || exit 1
VENV_PY="venv_mac/bin/python"

if [ ! -x "$VENV_PY" ] || [ ! -f .install_state.json ]; then
    echo "L'applicativo non e' ancora installato su questo Mac."
    echo "Scarica l'installer da: https://samugallo02.github.io/Nautilus_Website/"
    open "https://samugallo02.github.io/Nautilus_Website/" 2>/dev/null
    exit 1
fi

nohup "$VENV_PY" main.py >/dev/null 2>&1 &
disown
exit 0
