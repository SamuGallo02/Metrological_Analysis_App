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
python distribution/installer_gui.py --dest .      # oppure --cli senza finestra
python main.py        # con l'ambiente creato (venv / venv_mac / venv_linux)
```

Avvio rapido dopo l'installazione: `launchers/AnalisiMetrologica.vbs` (Windows), `launchers/AvviaAnalisiMetrologica.command` (macOS), `launchers/AvviaAnalisiMetrologica.sh` (Linux).
Gli extra per il training si installano dalla pagina *Training* dell'applicazione.

## Struttura

```text
assets/          risorse grafiche
config/          configurazione persistente (classi tracciate)
core/            algoritmi: analisi, calibrazione, pairing, tracking, report
gui/             interfaccia PySide6
training/        pagina e worker per l'addestramento di nuovi modelli YOLO
installer/       rilevamento OS/GPU, creazione venv, scelta build PyTorch
distribution/    sorgenti per generare gli installer (build_installer.py, installer_gui.py)
launchers/       avvio dell'applicazione per sistema operativo
tools/           demo webcam e acquisizione coppie di test
main.py          punto di ingresso
requirements.txt / requirements-training.txt
```

Non sono nel repository (vedi `.gitignore`): ambienti virtuali, pesi dei modelli (`*.pt`), dataset e immagini, file locali dell'installer.

## Dati operativi

- **Modelli YOLO** (`models/`): inserire i file `.pt` oppure importarli con "Aggiungi modello...".
- **Dataset stereo**: cartelle con le acquisizioni (nomi basati su timestamp), importabili con "Aggiungi cartella...".

## Uso

1. Scegliere il dataset e il modello YOLO dai menu in alto.
2. Scegliere la classe dell'oggetto da misurare.
3. "Avvia analisi", poi consultare immagini, lunghezza, larghezza e confidenza.
4. "Esporta CSV" per il report.

## Rigenerare gli installer

`python distribution/build_installer.py` crea `distribution/output/Installa.cmd` e `Installa.command` (non versionati: si pubblicano nel sito).
