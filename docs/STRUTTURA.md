# Struttura del progetto

Ogni sezione dell'applicazione ha una cartella `functions/` (logica, senza interfaccia) e una `gui/` (finestre PySide6).
Tutto ciò che è condiviso sta in `common/`.

| Cartella | Contenuto |
|---|---|
| `main.py` | punto di ingresso: lingua, accesso, finestra principale |
| `common/params.py` | parametri globali: nomi, lingue, ruoli, aree, campi del profilo, nomi delle cartelle dei dati |
| `common/paths/` | tutti i percorsi del progetto (dati locali, modelli, venv, icona) e la cartella dati dell'utente |
| `common/ambient/installer/` | installer: rileva sistema e GPU, crea il venv in `librery/`, sceglie PyTorch; `integrity.py` controlla i file del venv e `--repair` reinstalla solo i pacchetti danneggiati |
| `common/ambient/distribution/` | script per generare l'installer scaricabile |
| `common/translations/` | pacchetti lingua (it, es, de, fr, zh, ja); l'inglese è nel codice |
| `common/ui/` | widget comuni (barra superiore, immagini, layout) e selezione della lingua |
| `corpse/functions/analysis/` | algoritmi: analisi YOLO/stereo, calibrazione, abbinamento coppie, tracking, report CSV |
| `corpse/functions/training/` | parametri, hardware, worker di addestramento, gestione dell'ambiente |
| `corpse/functions/users/` | client: api, sessione, archivio locale, parametri |
| `corpse/functions/home/` | dati dell'hub delle 4 analisi |
| `corpse/gui/home/` | finestra principale, hub delle analisi, demo webcam |
| `corpse/gui/analysis/` | pagine foto, video, stereo e base comune |
| `corpse/gui/training/` | pagina di training, installazione delle estensioni, widget hardware |
| `corpse/gui/users/` | accesso, profilo, cartelle del server, amministrazione |
| `corpse/gui/manual/` | manuale d'uso |
| `datasets/Dataset_Locale/` | dati dell'utente: `dataset_Foto`, `dataset_Foto_Stereo`, `dataset_Video`, `dataset_Video_Stereo`, `dataset_Training`, `models`, `results`, `runs` |
| `librery/` | ambienti virtuali |
| `server/` | server HTTP, vedi `SERVER.md` |
| `tools/`, `tests/` | strumenti per sviluppatori e test |

Regole, verificate da `tests/test_isolation.py`: ogni sezione importa solo `common` e se stessa; la home è l'unica che
collega le altre; la logica (`functions`) e il server non importano Qt.
