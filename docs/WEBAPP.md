# Web app: l'applicazione dal browser

La web app è lo stesso server di `python -m server` con in più:

- le **pagine per il browser** su `/` (nessuna installazione per gli utenti: basta l'indirizzo del server);
- l'**analisi metrologica stereo eseguita sul server** (`/api/analysis/...`): YOLO + StereoSGBM come nella pagina
  *Analisi Stereo* dell'app desktop, con lo stesso codice (`corpse/functions/analysis`).

L'app desktop continua a funzionare con lo stesso server e gli stessi dati: le due cose convivono.

## Cosa c'è nel browser

| Sezione | Contenuto |
|---|---|
| Libreria | catalogo del materiale approvato (foto, stereo, video, modelli YOLO, dataset), con chi l'ha caricato e approvato; navigazione delle cartelle con anteprime e download |
| Analisi | scelta della cartella stereo (dalla libreria o da *La mia cartella*), del modello e della classe; baseline e focale; avanzamento in tempo reale, immagine con le maschere, misure per coppia e medie per soggetto, esportazione CSV (stesso formato del desktop) |
| Caricamenti | invio di foto, coppie stereo, video, modelli e dataset per la revisione; elenco dei propri invii con lo stato |
| La mia cartella | spazio personale sul server (quota): caricare file o cartelle, creare cartelle, eliminare |
| Migliora | correzione dei colori subacquea (vedi sotto): anteprima e confronto dei metodi, elaborazione a piena risoluzione di foto, cartelle e video |
| Team | team con cartella condivisa, membri e responsabili (vedi sotto) |
| Revisione, Utenti, Server | solo amministratori: approvare/rifiutare, gestire gli account, statistiche ed eventi |

Lingue: inglese e italiano per le pagine; gli errori del server sono tradotti in tutte le lingue dell'app (`common/translations`).

## Miglioramento delle immagini (Migliora)

Il nucleo di [underwater-image-enhancement](https://github.com/nautilus-unipd/underwater-image-enhancement) è copiato in
`nautilus/` (solo modelli, inferenza, metriche e video; non la sua interfaccia web). Metodi: *Colore e dettaglio bilanciati*
(WaterNet), *Acqua libera limpida*, *Colori vivaci, veloce* (FUnIE-GAN), *Ripristina il rosso perso* (fusione, senza IA),
*Contrasto rapido*. Usano la GPU se c'è (CUDA/ROCm, Intel XPU, OpenVINO), altrimenti il processore.

- **Da dove**: il pulsante *Migliora* su una foto, un video o una cartella (libreria, La mia cartella, cartella di un team).
- **Anteprima**: i metodi spuntati su una copia a 1280 px (per i video, sul fotogramma scelto), con le impostazioni di ogni
  metodo; confronto con cursore, affiancato o tutti insieme, punteggi UIQM/UCIQE. Le impostazioni restano nel browser.
- **Piena risoluzione**: un lavoro in coda (la stessa coda dell'analisi: un lavoro alla volta sulla GPU). Il risultato va
  **accanto all'originale**: `cattura/` → `cattura_waternet/` (stessa struttura, stessi nomi: le coppie lx/rx restano
  appaiate e le etichette YOLO `.txt`, `classes.txt` e `data.yaml` vengono copiate, perché il miglioramento cambia i colori,
  non la geometria); `foto.jpg` → `foto_waternet.jpg`; `immersione.mp4` → `immersione_waternet.mp4`. Gli elementi della
  libreria sono in sola lettura: il risultato va in *La mia cartella*. Vale la quota della cartella di destinazione.
- **Analisi**: *Migliora prima di misurare* applica lo stesso metodo (con le impostazioni scelte in Migliora) a entrambe le
  camere di ogni coppia, prima di YOLO e del matching stereo.

Pesi (non in git): `weights/waternet.pt` e `weights/funie_gan.pth` nella cartella del progetto, oppure nella cartella di
`NAUTILUS_WEIGHTS_DIR` (in Docker i pesi sono dentro l'immagine, in `/app/weights`). FUnIE-GAN si scarica con
`curl -L -o weights/funie_gan.pth https://raw.githubusercontent.com/xahidbuffon/FUnIE-GAN/master/PyTorch/models/funie_generator.pth`;
WaterNet si copia dal repository underwater-image-enhancement. Un metodo senza pesi compare come non installato.
Variabili utili: `NAUTILUS_DEVICE` (forza il dispositivo), `NAUTILUS_MAX_MEGAPIXELS` (tasselli di WaterNet, ~1,4 GB di
memoria per megapixel), `NAUTILUS_VIDEO_CRF` (qualità dei video, 18).

## Team

- **Chi li gestisce**: gli amministratori creano ed eliminano i team, scelgono i responsabili e la quota; i responsabili
  aggiungono e rimuovono i membri del proprio team; ognuno può uscire da un team. Un utente può stare in più team.
- **Cartella del team** (`store/teams/<nome del team>/`): ogni membro legge, carica, sposta ed elimina; quota per team
  (4 GB predefiniti). Le cartelle con `lx`/`rx` e i modelli che contiene si possono analizzare.
- **Visibilità nella libreria**: chi carica sceglie *Tutti gli utenti*, *Io e il team X* oppure *Solo io*, e può cambiarla
  dopo (pagina Caricamenti). Il server la applica a catalogo, elenco delle cartelle, download e analisi: chi non può vedere un
  elemento riceve 404. Gli amministratori vedono tutto. Ciò che esisteva prima dei team resta visibile a tutti.
- **Invii**: i membri vedono lo stato dei caricamenti condivisi con il loro team (*Miei e dei miei team*).
- **Analisi**: *Chi può vedere i risultati* → un team; i membri vedono i risultati e scaricano il CSV, solo chi l'ha avviata la
  ferma o la elimina.
- **Eliminare un team** cancella la sua cartella; i caricamenti condivisi solo con quel team diventano visibili solo a chi li
  ha caricati (mai più aperti di prima).

## Avvio

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu   # oppure .../cu121 con GPU NVIDIA
pip install -r webapp/requirements.txt
python -m webapp create-admin NOME          # solo la prima volta (stessi comandi di `python -m server`)
python -m webapp serve                      # poi apri http://127.0.0.1:8765
python -m webapp serve --lan                # dagli altri dispositivi della rete
```

Senza OpenCV/PyTorch/Ultralytics la web app parte comunque: libreria, caricamenti e amministrazione funzionano, e la pagina
Analisi dice quale libreria manca.

## Docker (tutto in un contenitore)

L'immagine contiene tutto: server, pagine, analisi (OpenCV, YOLO), miglioramento (nautilus, con i pesi presenti in
`weights/` al momento del build) e video. Sull'host serve solo Docker (e, per la GPU, il driver NVIDIA ≥ 530 con il
NVIDIA Container Toolkit). PyTorch 2.5.1 + CUDA 12.1 funziona anche con schede vecchie (Maxwell, es. Quadro M4000).

```bash
# con GPU NVIDIA (immagine ~6 GB)
docker compose -f deploy/docker-compose.web.yml -f deploy/docker-compose.gpu.yml up -d --build
# solo CPU (immagine più piccola)
TORCH_INDEX=https://download.pytorch.org/whl/cpu docker compose -f deploy/docker-compose.web.yml up -d --build

docker compose -f deploy/docker-compose.web.yml exec webapp python -m webapp --data /data create-admin NOME
```

Poi apri `http://127.0.0.1:8765`. Impostazioni (variabili d'ambiente o un file `.env` accanto ai compose):

| Variabile | Predefinito | |
|---|---|---|
| `AM_DATA_DIR` | volume `analisi-data` | dove stanno i dati; una cartella della macchina deve appartenere all'utente 10001 (`sudo chown -R 10001 CARTELLA`) |
| `AM_BIND` | `127.0.0.1` | indirizzo su cui si pubblica la porta: `127.0.0.1` con un proxy sulla macchina (`tailscale serve`, Caddy), l'indirizzo Tailscale `100.x.y.z`, oppure `0.0.0.0` per tutta la rete |
| `AM_PORT` | `8765` | porta sull'host |
| `AM_ADMIN_KEY` | vuota | chiave di accesso amministratore |
| `NAUTILUS_MAX_MEGAPIXELS` | `4` | tasselli di WaterNet (~1,4 GB di memoria GPU per megapixel) |

Con Tailscale: lascia `AM_BIND=127.0.0.1` e pubblica con `tailscale serve --bg 8765` (HTTPS su
`https://<macchina>.<tailnet>.ts.net`). Il servizio `backup` copia ogni giorno database e file in `/data/backups` (ultime 7).
Per portare tutto su un'altra macchina basta il volume (o la cartella `AM_DATA_DIR`): `docker run --rm -v
analisi-web_analisi-data:/data -v "$PWD":/out alpine tar czf /out/analisi-data.tgz -C /data .` e il contrario per ripristinarlo.
Aggiornare: `git pull` e di nuovo `up -d --build` (i dati restano nel volume).

## Sicurezza

- **Nuovi account da approvare**: il contenitore avvia il server con `--approve-register`. Chi si registra dalla
  pagina di accesso resta *in attesa di approvazione* finché un amministratore non preme **Approva** in *Utenti*
  (oppure `python -m webapp --data /data users enable NOME`). Chi si registra con la chiave amministratore entra subito.
  Fuori dal contenitore la registrazione resta libera se non si passa `--approve-register` (o `--no-register`).
- **Modelli YOLO**: un file `.pt` è un archivio pickle e può eseguire codice quando viene caricato. L'analisi carica i
  `.pt` solo dalla libreria dei modelli (approvati da un amministratore); dalla propria cartella o da quella di un team si
  possono usare solo modelli `.onnx`.
- **Visibilità**: gli elementi privati o di un altro team non si leggono né scaricando con percorsi scritti in modo
  diverso (`a//b`, `a/./b`, `a\b`) né migliorando la cartella che li contiene: il lavoro li salta.

## Come funziona l'analisi

- Una sola coda per tutto il server, un'analisi alla volta (la GPU è condivisa); ogni utente può avere una sola analisi in corso.
- I risultati (JSON e un'immagine per coppia) stanno in `<cartella dati>/web_jobs/<id>/`: restano 24 ore, al massimo 20 per
  utente, e vengono cancellati al riavvio del server.
- A differenza dell'app desktop, l'analisi **non scrive** i file di etichette accanto alle foto: la libreria è condivisa.
- Un utente può analizzare solo ciò che può già leggere: la libreria approvata e la propria cartella (gli amministratori anche
  i caricamenti in attesa).
- Per analizzare acquisizioni proprie: *La mia cartella* → *Carica una cartella* con le sottocartelle `lx` e `rx`.

## API aggiunte

Tutte richiedono `Authorization: Bearer <token>` (tranne `/api/i18n`).

| Metodo e percorso | |
|---|---|
| `GET /api/analysis/status` | `{available, device, reason, defaults}` |
| `GET /api/analysis/classes?area=&path=` | classi del modello (`.pt` solo dalla libreria `models`, `.onnx` anche da cartella personale o team) |
| `POST /api/analysis/jobs` | `{source:{area,path}, model:{area,path}, label, baseline_mm, focal_length_px, detect_right}` → `{job}` |
| `GET /api/analysis/jobs` | le proprie analisi |
| `GET /api/analysis/jobs/<id>?since=N` | stato e risultati dalla coppia N in poi |
| `GET /api/analysis/jobs/<id>/overlay/<i>` | immagine JPEG della coppia i |
| `GET /api/analysis/jobs/<id>/csv` | report CSV |
| `POST /api/analysis/jobs/<id>/cancel`, `DELETE /api/analysis/jobs/<id>` | ferma / elimina |
| `GET /api/i18n?lang=it` | traduzioni per le pagine |
| `GET /api/enhance/status` | metodi (con parametri), dispositivo, supporto video |
| `POST /api/enhance/preview` | `{source:{area,path}, methods:[{id, params}], seconds}` → immagini (data URL) e punteggi |
| `POST /api/enhance/jobs` | `{source:{area,path}, method, params}` → lavoro; `output` dice dove va il risultato |
| `GET /api/enhance/jobs[/<id>]`, `POST …/<id>/cancel`, `DELETE …/<id>` | come per l'analisi |

API dei team (nel server, disponibili anche all'app desktop):

| Metodo e percorso | |
|---|---|
| `GET /api/teams` | i propri team (amministratori: tutti), con membri, ruolo e spazio usato |
| `POST /api/teams` | amministratori: `{name, leader, quota_mb}` |
| `PATCH /api/teams/<id>`, `DELETE /api/teams/<id>` | amministratori: quota / eliminazione |
| `POST /api/teams/<id>/members` | `{username, role}`: responsabili (ruolo `member`) e amministratori |
| `PATCH /api/teams/<id>/members/<uid>` | amministratori: `{role: leader\|member}` |
| `DELETE /api/teams/<id>/members/<uid>` | responsabili (membri), amministratori, o se stessi |
| `PATCH /api/species/submissions/<id>` | chi ha caricato o un amministratore: `{visibility: public\|team\|private, team_id}` |
| file con `area=teams&path=<team>/...` | cartella del team, con le stesse route dei file |

Gli invii (`/api/species/submit`, `/api/datasets/submit`, `/api/models/submit`) accettano `visibility` e `team_id`
(predefinito: tutti); `GET /api/species/submissions?include=teams` aggiunge gli invii condivisi con i propri team;
`POST /api/analysis/jobs` accetta `team_id`.

## Struttura

```text
webapp/
  __main__.py     python -m webapp: i comandi di server/__main__.py con il gestore web
  handler.py      WebHandler (sottoclasse di server.app.Handler): pagine, traduzioni, route dell'analisi
  jobs.py         coda delle analisi (solo libreria standard) e report CSV
  engine.py       l'analisi vera: corpse.functions.analysis, importato solo quando serve
  enhance.py      il miglioramento delle immagini (nautilus): anteprime e lavori
  static/         index.html, app.js, style.css, i18n/it.json (nessun framework, nessun build)
```

Il server (`server/`) non importa la web app: `make_server(..., handler_base=WebHandler)` è l'unico punto di aggancio.
Test: `python -m unittest tests.test_webapp tests.test_teams tests.test_enhance` (con un motore finto: girano senza OpenCV, anche in CI).
