#!/bin/bash
# ==============================================================================
# Installer per macOS - Analisi Metrologica
# ==============================================================================
# Da eseguire una sola volta (doppio clic). Installa SOLO cio' che serve a questo
# Mac: Python 3.10+ se manca (Homebrew se presente, altrimenti pacchetto ufficiale
# python.org: chiede la password del Mac), l'ambiente virtuale "venv_mac" e i
# componenti base (PyTorch con supporto Apple GPU/MPS integrato + librerie).
# Il training non richiede componenti aggiuntivi su Mac. Esito registrato in
# .install_state.json: gli avvii successivi non controllano piu' nulla.
# Opzione: ./Installa_macOS.command --force  per reinstallare.
#
# Prima volta: se macOS blocca il file ("sviluppatore non identificato"), clic
# destro > Apri > Apri; oppure da Terminale: xattr -dr com.apple.quarantine <cartella>
#
# Autore: Samuele Gallo
# ==============================================================================

cd "$(dirname "$0")" || exit 1
PY_VERSION="3.12.6"
PY_PKG_URL="https://www.python.org/ftp/python/$PY_VERSION/python-$PY_VERSION-macos11.pkg"

pause_and_exit() { echo; read -n 1 -s -r -p "Premi un tasto per chiudere..."; echo; exit "${1:-1}"; }

if [ "$(uname -s)" != "Darwin" ]; then
    echo "ERRORE: questo installer e' per macOS. Su Linux usa Installa_Linux.sh, su Windows Installa_Windows.vbs."
    pause_and_exit 1
fi
if [ ! -f main.py ] || [ ! -d installer ]; then
    echo "ERRORE: file del progetto mancanti (main.py o cartella installer). Scarica l'intera cartella."
    pause_and_exit 1
fi

python_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; }

find_python() {
    local cand p
    for cand in python3.13 python3.12 python3.11 python3.10 python3; do
        p="$(command -v "$cand" 2>/dev/null)"
        if [ -n "$p" ] && [ "$p" != "/usr/bin/python3" ] && python_ok "$p"; then echo "$p"; return 0; fi
    done
    for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/3.*/bin/python3; do
        if [ -x "$p" ] && python_ok "$p"; then echo "$p"; return 0; fi
    done
    return 1
}

install_python() {
    echo "Nessun Python 3.10+ trovato: installo Python $PY_VERSION."
    if command -v brew >/dev/null 2>&1; then
        brew install python@3.12 || return 1
    else
        local pkg="/tmp/python-$PY_VERSION.pkg"
        curl -L --fail -o "$pkg" "$PY_PKG_URL" || return 1
        sudo installer -pkg "$pkg" -target / || return 1
        rm -f "$pkg"
    fi
}

SYS_PY="$(find_python)"
if [ -z "$SYS_PY" ]; then
    install_python || { echo "Installazione di Python non riuscita. Installalo da https://www.python.org/downloads/ e riesegui."; pause_and_exit 1; }
    SYS_PY="$(find_python)"
    [ -z "$SYS_PY" ] && { echo "Python installato ma non trovato: chiudi e riapri Terminale, poi riesegui."; pause_and_exit 1; }
fi

echo "Uso Python: $SYS_PY"
"$SYS_PY" -m installer --os macos --component core --yes "$@"
RC=$?
if [ $RC -ne 0 ] || [ ! -f .install_state.json ]; then
    echo; echo "Installazione non riuscita. Dettagli in: $(pwd)/install_log.txt"
    pause_and_exit 1
fi
echo; echo "Installazione completata. Avvia l'app con AvviaAnalisiMetrologica.command"
pause_and_exit 0
