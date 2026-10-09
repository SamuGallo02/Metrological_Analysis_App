#!/bin/bash
# Application launcher (Linux). Installation is done only once with the installer
# downloadable from the website; nothing is checked here.
cd "$(dirname "$0")/../.." || exit 1
if [ ! -x librery/venv_linux/bin/python ] || [ ! -f librery/.install_state.json ]; then
    echo "L'applicativo non e' installato. Scarica l'installer da: https://samugallo02.github.io/Nautilus_Website/"
    exit 1
fi
nohup librery/venv_linux/bin/python main.py >/dev/null 2>&1 &
disown
