# Analisi Stereo-Fotogrammetrica Metrologica (Computer Vision e YOLO)

**[⬇ Scarica l'installer (Windows · macOS · Linux)](https://samugallo02.github.io/Nautilus_Website/)**

Progetto di tesi: pipeline software per la stima metrologica e tridimensionale di oggetti a partire da coppie di fotogrammi stereo.
Modelli di segmentazione (**YOLO**) e stereovisione (**Stereo SGBM**) calcolano la disparità locale, la profondità mediana (Z) e le dimensioni di ingombro (L × W × H) in mm e cm dell'oggetto scelto. L'interfaccia è in **PySide6**, con le elaborazioni in thread dedicati (`QThread`).

## Requisiti

- Windows 10/11, macOS o Linux, con **Python 3.10 o successivo** (con tkinter per la finestra dell'installer).
- Spazio libero: circa 3 GB; con scheda NVIDIA circa 10 GB (PyTorch con supporto GPU).
- Connessione a internet durante l'installazione.

## Installazione

Scarica l'installer per il tuo sistema operativo (Windows, macOS, Linux) dal sito: <https://samugallo02.github.io/Nautilus_Website/>.
L'installer chiede la cartella di destinazione, scarica il codice da questo repository e solo le librerie adatte al tuo computer (PyTorch con GPU NVIDIA se presente) e crea il collegamento sul Desktop. I componenti già presenti non vengono riscaricati.

Installazione manuale da sorgente (sviluppo):

```bash
git clone https://github.com/SamuGallo02/Metrological_Analysis_App.git
cd Metrological_Analysis_App
python common/ambient/distribution/installer_gui.py --dest .      # oppure --cli senza finestra
python main.py        # all'avvio controlla i file del venv e propone la riparazione se qualcosa è danneggiato (`--no-check` per saltare); con l'ambiente creato (librery/venv, librery/venv_mac, librery/venv_linux)
```

Avvio rapido dopo l'installazione: `common/launchers/AnalisiMetrologica.vbs` (Windows), `common/launchers/AvviaAnalisiMetrologica.command` (macOS), `common/launchers/AvviaAnalisiMetrologica.sh` (Linux).
Gli extra per il training si installano dalla pagina *Training* dell'applicazione.

## Struttura

```text
main.py                 punto di ingresso
common/                 parti condivise da tutte le sezioni
  ambient/              installer (installer/), librerie richieste (requirements/) e script per gli installer (distribution/)
  assets/ config/       icona e configurazione persistente (classi tracciate)
  errors/ paths/ security/ settings/   errori, percorsi, sicurezza e impostazioni
  translations/         pacchetti lingua (it, es, de, fr, zh, ja); l'inglese e' nel codice
  launchers/            avvio dell'applicazione per sistema operativo
  ui/                   widget comuni e selezione della lingua
  params.py             parametri globali (nomi, lingue, indirizzi, cartelle)
corpse/                 il cuore dell'applicazione
  functions/            logica, senza interfaccia: analysis, home, training, users
  gui/                  interfaccia PySide6: analysis, home, manual, training, users
datasets/Dataset_Locale/  dati dell'utente: foto, video, dataset di training, modelli, risultati
librery/                ambienti virtuali creati dall'installer (venv, venv_mac, venv_linux)
server/                 server HTTP per account e cartelle condivise (non installato dagli utenti)
tools/                  demo webcam, acquisizione coppie di test, generazione dei pacchetti lingua
tests/  docs/           test automatici e documentazione
common/ambient/requirements/  elenco delle librerie (core e training)
```

Ogni sezione importa solo `common` e se stessa (verificato da `tests/test_isolation.py`); la home e' l'unica che le collega.

Non sono nel repository (vedi `.gitignore`): ambienti virtuali, pesi dei modelli (`*.pt`), dataset e immagini, file locali dell'installer, chiave del server.

## Dati operativi

- **Modelli YOLO** (`datasets/Dataset_Locale/models/`): inserire i file `.pt` oppure importarli con "Aggiungi modello...".
- **Dataset stereo**: cartelle con le acquisizioni (nomi basati su timestamp), importabili con "Aggiungi cartella...".

## Uso

1. Scegliere il dataset e il modello YOLO dai menu in alto.
2. Scegliere la classe dell'oggetto da misurare.
3. "Avvia analisi", poi consultare immagini, lunghezza, larghezza e confidenza.
4. "Esporta CSV" per il report.

## Account, server e lingue

- Al primo avvio si accede con un account, si usa l'app come ospite (offline) o si crea un account. Con la chiave di accesso corretta l'account diventa amministratore in modo permanente; dopo 5 tentativi errati la chiave è bloccata per 5 minuti (il server resta attivo).
- La chiave non sta nel codice: si imposta sul server con `AM_ADMIN_KEY` oppure `server/admin_key.txt` (ignorato da git) o con l'hash `python -m server hash-key`. Dettagli in `docs/SERVER.md`.
- La lingua base è l'inglese; le altre (italiano, spagnolo, tedesco, francese, cinese, giapponese) si scaricano dal Profilo. I pacchetti si generano con `python -m tools.build_language_packs --out site/locales` e si pubblicano nel sito.
- Dal Profilo si modificano i propri dati e si gestiscono le cartelle.

## Rigenerare gli installer

`python common/ambient/distribution/build_installer.py` crea `common/ambient/distribution/output/Installa.cmd` e `Installa.command` (non versionati: si pubblicano nel sito).
