# Analisi Stereo-Fotogrammetrica Metrologica basata su Computer Vision e YOLO

## 1. Descrizione del Progetto

Il presente progetto costituisce il lavoro di tesi incentrato sullo sviluppo di una pipeline software per la stima metrologica e tridimensionale di oggetti a partire da fotogrammi stereo.

L'architettura integra modelli di Deep Learning per l'istanziamento e la segmentazione semantica (**YOLOv11**) con algoritmi di stereovisione (**Stereo SGBM**). Il sistema calcola la mappa di disparità locale, stima la profondità mediana ($Z$) rispetto all'asse ottico ed estrae le dimensioni metriche di ingombro ($L \times W \times H$) espresse in millimetri e centimetri per l'oggetto target selezionato.

L'interfaccia grafica è realizzata in **PySide6 (Qt per Python)** per garantire un'esperienza utente reattiva, modularizzata e ottimizzata nell'esecuzione asincrona delle elaborazioni tramite thread dedicati (`QThread`).

---

## 2. Architettura del Progetto ed Elementi Esclusi da Git

Per superare i limiti di dimensione previsti da GitHub (max 100 MB per file / 2 GB per repository), **tutti gli elementi di grandi dimensioni e file di configurazione locale sono stati esclusi dal tracciamento Git tramite file `.gitignore`**.

### Elementi Esclusi dal Repository

1. `venv/`: Ambiente virtuale Python con le librerie installate (PyTorch, PySide6, OpenCV, Ultralytics).
2. `datasets/`: Cartella contenente le immagini e i fotogrammi stereo di acquisizione.
3. `models/*.pt`: File di pesi dei modelli neurali di segmentazione YOLO.
4. `.idea/`: Directory di configurazione dell'ambiente di sviluppo PyCharm.
5. `.installed`: File di cache e stato locale dell'ambiente.

### Struttura del Codice Sorgente Tracciato

```text
Applicativo/
├── assets/                  # Risorse grafiche ed elementi di branding GUI
├── core/                    # Core logico e algoritmi di elaborazione
│   ├── analysis.py          # Pipeline metrologica, segmentazione e stima 3D
│   ├── object_classes.py    # Gestione dinamica del registro delle classi target
│   ├── pairing.py           # Algoritmo di associazione e sincronizzazione coppie stereo
│   └── reporting.py         # Calcolo degli indici statistici ed esportazione dati
├── gui/                     # Interfaccia Utente (PySide6)
│   └── main_window.py       # Finestra principale e gestione thread di analisi (QThread)
├── tools/                   # Utility di diagnostica e acquisizione test
├── AnalisiMetrologica.vbs   # Launcher VBScript per l'avvio silenzioso senza console
├── main.py                  # Entry-point principale per l'avvio dell'applicazione
├── object_classes.json      # Configurazione persistente delle classi tracciate
├── requirements.txt         # Dipendenze software Python
└── README.md                # Documentazione formale del repository


## 2. Comandi BASH (Setup, Esecuzione e GIT)

# 1. Clonazione del repository
git clone [https://github.com/USERNAME/NOME_REPOSITORY.git](https://github.com/USERNAME/NOME_REPOSITORY.git)
cd NOME_REPOSITORY

# 2. Creazione dell'ambiente virtuale
python -m venv venv

# 3. Attivazione dell'ambiente virtuale
# Su Windows (PowerShell / Bash):
source venv/Scripts/activate
# Su Linux / macOS:
source venv/bin/activate

# 4. Aggiornamento pip e installazione dipendenze
pip install --upgrade pip
pip install -r requirements.txt

# 5. Ricreazione delle directory locali per modelli e dataset
mkdir -p models datasets


#-----


Con l'ambiente virtuale attivo, avvia l'applicazione con il seguente comando bash:
python main.py
In alternativa alla riga di comando, una volta creato l'ambiente venv è possibile avviare l'applicazione facendo doppio clic sul file AnalisiMetrologica.vbs.


5. Preparazione dei Dati Operativi
Poiché i file pesanti e i modelli non sono inclusi nel repository Git, posizionali nelle relative directory locali prima di avviare le analisi:

Modelli YOLO (models/): Posizionare i file dei pesi .pt (es. yolo11s-seg.pt) nella cartella models/ oppure importarli tramite il pulsante "Aggiungi modello..." nell'interfaccia.

Dataset Stereo (datasets/): Posizionare le cartelle contenenti le acquisizioni stereo (con nomenclatura basata su timestamp) nella cartella datasets/ oppure importarle tramite il pulsante "Aggiungi cartella...".


6. Procedura Operativa dell'Utente
Selezionare il Dataset: Scegliere la cartella con le coppie stereo dal menu a tendina in alto.

Selezionare il Modello YOLO: Scegliere il file .pt presente nella directory models/.

Selezionare l'Oggetto: Scegliere dal menu a tendina la classe specifica dell'oggetto da sottoporre a scansione metrologica.

Eseguire l'Analisi: Cliccare sul pulsante "Avvia analisi" posizionato sotto la selezione dell'oggetto.

Esportare i Risultati: Consultare le immagini elaborate nel pannello centrale, verificare i valori di lunghezza, larghezza e confidenza nella tabella a destra ed esportare il report finale cliccando su "Esporta CSV".
