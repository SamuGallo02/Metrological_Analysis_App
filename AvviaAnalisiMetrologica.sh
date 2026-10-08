#!/bin/bash
# Avvio dell'applicativo (Linux). Nessun controllo di dipendenze: l'installazione
# si fa una volta sola con ./Installa_Linux.sh.
cd "$(dirname "$0")" || exit 1
if [ ! -x venv_linux/bin/python ] || [ ! -f .install_state.json ]; then
    echo "L'applicativo non e' installato. Esegui prima:  ./Installa_Linux.sh"
    exit 1
fi
nohup venv_linux/bin/python main.py >/dev/null 2>&1 &
disown
