#!/bin/bash
# ==============================================================================
# Launcher per macOS (equivalente di AnalisiMetrologica.vbs, che e' solo Windows)
# ==============================================================================
# Doppio clic da Finder: apre Terminal ed esegue questo script. Al primo avvio
# su un nuovo Mac crea da solo l'ambiente virtuale (cartella "venv_mac", separata
# dal "venv" di Windows cosi' i due non si pestano i piedi se la cartella del
# progetto e' condivisa) e installa tutte le dipendenze, PyTorch incluso, tramite
# setup.py. Se manca un Python 3.10+ lo installa da solo (Homebrew se presente,
# altrimenti il pacchetto ufficiale da python.org: in quel caso Terminal chiede
# la password del Mac, una volta sola). Dagli avvii successivi parte subito.
#
# NOTA: la prima volta macOS puo' bloccare il file ("sviluppatore non
# identificato"): clic destro sul file > Apri > Apri. Se Finder dice che non hai
# i permessi di esecuzione, da Terminale nella cartella del progetto:
#     chmod +x AvviaAnalisiMetrologica.command
# Per usare la webcam, macOS chiedera' di consentire l'accesso alla fotocamera a
# Terminale: accetta.
#
# Autore: Samuele Gallo
# ==============================================================================

cd "$(dirname "$0")" || exit 1
PROJECT_DIR="$(pwd)"
VENV_DIR="$PROJECT_DIR/venv_mac"
VENV_PY="$VENV_DIR/bin/python"
MARKER="$VENV_DIR/.setup_complete"
PY_VERSION="3.12.6"
PY_PKG_URL="https://www.python.org/ftp/python/$PY_VERSION/python-$PY_VERSION-macos11.pkg"

pause_and_exit() {
    echo
    read -n 1 -s -r -p "Premi un tasto per chiudere..."
    echo
    exit "${1:-1}"
}

if [ ! -f "$PROJECT_DIR/main.py" ]; then
    echo "ERRORE: main.py non trovato in $PROJECT_DIR."
    echo "Controlla di aver scaricato l'intera cartella del progetto, non solo questo file."
    pause_and_exit 1
fi

# Restituisce 0 se l'interprete passato e' Python >= 3.10
python_ok() {
    "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

# Cerca un Python 3.10+ in posizioni note (salta /usr/bin/python3: e' lo stub di
# Xcode, vecchio e puo' far comparire un popup di installazione degli strumenti).
find_python() {
    local cand
    for cand in python3.13 python3.12 python3.11 python3.10 python3; do
        local p
        p="$(command -v "$cand" 2>/dev/null)"
        if [ -n "$p" ] && [ "$p" != "/usr/bin/python3" ] && python_ok "$p"; then
            echo "$p"; return 0
        fi
    done
    for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
             /Library/Frameworks/Python.framework/Versions/3.*/bin/python3; do
        if [ -x "$p" ] && python_ok "$p"; then
            echo "$p"; return 0
        fi
    done
    return 1
}

install_python() {
    echo "Nessun Python 3.10+ trovato: lo installo automaticamente (Python $PY_VERSION)."
    if command -v brew >/dev/null 2>&1; then
        echo "Uso Homebrew..."
        brew install python@3.12 || return 1
    else
        echo "Scarico il pacchetto ufficiale da python.org (richiede la password del Mac)..."
        local pkg="/tmp/python-$PY_VERSION.pkg"
        curl -L --fail -o "$pkg" "$PY_PKG_URL" || return 1
        sudo installer -pkg "$pkg" -target / || return 1
        rm -f "$pkg"
    fi
    return 0
}

if [ ! -f "$MARKER" ] || [ ! -x "$VENV_PY" ]; then
    if [ ! -f "$PROJECT_DIR/setup.py" ]; then
        echo "ERRORE: setup.py non trovato in $PROJECT_DIR."
        echo "Controlla di aver scaricato l'INTERA cartella del progetto da GitHub."
        pause_and_exit 1
    fi

    SYS_PY="$(find_python)"
    if [ -z "$SYS_PY" ]; then
        install_python || {
            echo
            echo "Installazione automatica di Python non riuscita (connessione assente o password errata)."
            echo "Installalo a mano da https://www.python.org/downloads/ e riesegui questo file."
            pause_and_exit 1
        }
        SYS_PY="$(find_python)"
        if [ -z "$SYS_PY" ]; then
            echo "Python risulta installato ma non lo trovo: chiudi e riapri Terminale, poi riesegui."
            pause_and_exit 1
        fi
    fi

    echo "Uso Python: $SYS_PY ($("$SYS_PY" --version))"
    echo "Creazione dell'ambiente virtuale in $VENV_DIR ..."
    rm -rf "$VENV_DIR"
    "$SYS_PY" -m venv "$VENV_DIR" || { echo "Creazione dell'ambiente virtuale non riuscita."; pause_and_exit 1; }

    echo "Installazione delle dipendenze (puo' richiedere diversi minuti)..."
    "$VENV_PY" setup.py 2>&1 | tee "$PROJECT_DIR/setup_log.txt"
    if [ "${PIPESTATUS[0]}" -ne 0 ]; then
        echo
        echo "Installazione non riuscita. Dettagli in: $PROJECT_DIR/setup_log.txt"
        pause_and_exit 1
    fi

    echo "Setup completato con successo." > "$MARKER"
    echo "Configurazione completata."
fi

# Avvio dell'app staccata dal terminale, cosi' si puo' chiudere la finestra di Terminal
nohup "$VENV_PY" "$PROJECT_DIR/main.py" >/dev/null 2>&1 &
disown
exit 0
