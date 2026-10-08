#!/bin/bash
# Avvio dell'applicativo (macOS). Nessun controllo di dipendenze ad ogni avvio:
# l'installazione si fa una volta sola con Installa_macOS.command (esito in
# .install_state.json). Se non risulta installato, propone di eseguirla.

cd "$(dirname "$0")/.." || exit 1
VENV_PY="venv_mac/bin/python"

if [ ! -x "$VENV_PY" ] || { [ ! -f .install_state.json ] && [ ! -f venv_mac/.setup_complete ]; }; then
    echo "L'applicativo non e' ancora installato su questo Mac."
    read -r -p "Avviare ora l'installazione? [S/n] " ans
    case "$ans" in [nN]*) exit 0 ;; esac
    bash launchers/Installa_macOS.command || exit 1
    [ -x "$VENV_PY" ] || exit 1
fi

nohup "$VENV_PY" main.py >/dev/null 2>&1 &
disown
exit 0
