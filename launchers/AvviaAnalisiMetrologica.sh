#!/bin/bash
# Avvio dell'applicativo (Linux). L'installazione si fa una volta sola con l'installer
# scaricabile dal sito; qui non si controlla nulla.
cd "$(dirname "$0")/.." || exit 1
if [ ! -x venv_linux/bin/python ] || [ ! -f .install_state.json ]; then
    echo "L'applicativo non e' installato. Scarica l'installer da: https://samugallo02.github.io/Nautilus_Website/"
    exit 1
fi
nohup venv_linux/bin/python main.py >/dev/null 2>&1 &
disown
