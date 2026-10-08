#!/bin/bash
# ==============================================================================
# Installer per LINUX - Analisi Metrologica
# ==============================================================================
# Da eseguire una sola volta:  ./Installa_Linux.sh   (opzione: --force)
# Installa SOLO cio' che serve a questo computer: Python 3.10+ e il modulo venv
# se mancano (tramite apt/dnf/pacman, richiede sudo), l'ambiente "venv_linux" e i
# componenti base (PyTorch con CUDA se c'e' una GPU NVIDIA, altrimenti CPU leggera,
# + librerie). Solo gli extra del training si installano dall'app, su richiesta.
# Esito registrato in .install_state.json: gli avvii successivi non controllano nulla.
#
# Autore: Samuele Gallo
# ==============================================================================

cd "$(dirname "$0")" || exit 1

if [ "$(uname -s)" != "Linux" ]; then
    echo "ERRORE: questo installer e' per Linux. Su macOS usa Installa_macOS.command, su Windows Installa_Windows.vbs."
    exit 1
fi
if [ ! -f main.py ] || [ ! -d installer ]; then
    echo "ERRORE: file del progetto mancanti (main.py o cartella installer). Scarica l'intera cartella."
    exit 1
fi

python_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; }
venv_ok()   { "$1" -c 'import venv, ensurepip' >/dev/null 2>&1; }

find_python() {
    local cand p
    for cand in python3.13 python3.12 python3.11 python3.10 python3; do
        p="$(command -v "$cand" 2>/dev/null)"
        if [ -n "$p" ] && python_ok "$p"; then echo "$p"; return 0; fi
    done
    return 1
}

install_python() {
    echo "Installo Python 3 e il modulo venv (serve sudo)..."
    if   command -v apt-get >/dev/null 2>&1; then sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
    elif command -v dnf     >/dev/null 2>&1; then sudo dnf install -y python3 python3-pip
    elif command -v pacman  >/dev/null 2>&1; then sudo pacman -S --noconfirm python python-pip
    elif command -v zypper  >/dev/null 2>&1; then sudo zypper install -y python3 python3-pip
    else echo "Gestore pacchetti non riconosciuto."; return 1
    fi
}

SYS_PY="$(find_python)"
if [ -z "$SYS_PY" ] || ! venv_ok "$SYS_PY"; then
    install_python || { echo "Installa a mano Python 3.10+ (con il modulo venv) e riesegui."; exit 1; }
    SYS_PY="$(find_python)"
    if [ -z "$SYS_PY" ] || ! venv_ok "$SYS_PY"; then
        echo "Python 3.10+ con venv non disponibile dopo l'installazione: la tua distribuzione potrebbe averne uno piu' vecchio."
        exit 1
    fi
fi

echo "Uso Python: $SYS_PY"
"$SYS_PY" -m installer --os linux --component core --yes "$@"
if [ $? -ne 0 ] || [ ! -f .install_state.json ]; then
    echo; echo "Installazione non riuscita. Dettagli in: $(pwd)/install_log.txt"
    exit 1
fi
echo; echo "Installazione completata. Avvia l'app con ./AvviaAnalisiMetrologica.sh"
