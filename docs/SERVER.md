# Server: avvio e messa online

Solo libreria standard di Python 3.10+ (nessuna installazione, nessuna interfaccia grafica).

```
python -m server create-admin NOME                            # chiede la password (min 8 caratteri)
python -m server serve --host 0.0.0.0 --port 8765
python -m server serve --no-register                          # solo l'amministratore crea gli account
python -m server serve --trust-proxy                          # dietro Caddy/nginx: IP reale da X-Forwarded-For
python -m server hash-key                                     # stampa sha256:<hex> da mettere al posto della chiave
python -m server serve --lan                                  # raggiungibile da altri dispositivi della rete (test)
python -m server doctor | status | backup | users list        # gestione e manutenzione
```
Test su altri dispositivi, accesso da Internet con tunnel HTTPS, Docker, systemd, backup automatico e tutti i comandi di
gestione: vedi **`deploy/README.md`**.

## Dati: come il server salva i file
Il server tiene i suoi file in `<cartella dati>/store/`, separati da come l'app li mostra (le cartelle locali dell'app non
c'entrano). Senza `--data` la cartella dati è `datasets/server_data/`, separata dai dati locali dell'app (`datasets/Dataset_Locale/`).

| Cartella | Contenuto |
|---|---|
| `store/library/photos/<Specie>/` | foto approvate (con le etichette `.txt`) |
| `store/library/stereo/<Specie>/<lx\|rx>/` | coppie stereo approvate |
| `store/library/videos/<Specie>/` | video approvati (con le etichette `.txt`) |
| `store/library/stereo_videos/<Specie>/<lx\|rx>/` | coppie di video stereo approvate |
| `store/library/models/<Specie>/` | modelli YOLO approvati (+ `.json`) |
| `store/library/datasets/` | dataset di addestramento |
| `store/pending/<area>/<utente>/` | caricamenti in attesa di approvazione (quarantena unica) |
| `store/mine/<utente>/` | cartella personale di ogni utente |

Il database (utenti, sessioni, registro, **cronologia dei caricamenti** con chi ha caricato e chi ha approvato) è `server.db`
nella cartella dati. Non c'è una tabella per file: caricamento, approvazione e data valgono per tutto il lotto.

- **Caricamenti**: tutti (anche gli amministratori) finiscono in `store/pending/`; l'approvazione sposta i file in
  `store/library/` (rinominati IMG_0001, VID_0001… con le loro etichette), il rifiuto li elimina. La cronologia resta.
- **Etichette**: ogni foto o video può avere un file `.txt` accanto (formato YOLO; nei video la prima colonna è il numero del
  fotogramma) e un `classes.txt` con i nomi delle classi. L'analisi metrologica le salva da sola e vengono caricate insieme al file.
- **Migrazione**: al primo avvio `server.db`, `store/`, `logs/` e `backups/` che stavano in `datasets/Dataset_Locale/` passano in `datasets/server_data/` (le cartelle dell'app non si toccano); poi le vecchie cartelle (`dataset_Specie`, `_pending`, `users/`…) vengono spostate nella nuova
  struttura. Fai prima una copia della cartella dati.
- **Dataset**: le cartelle caricate dagli utenti vengono inserite nei dataset del server; i file già presenti non si sovrascrivono.
- **Backup**: copia `datasets/server_data` a server fermo, oppure solo `server.db` con `sqlite3 server.db ".backup copia.db"`.
- Per usare un'altra cartella: `python -m server --data PERCORSO serve`.

## Chiave di accesso amministratore
- Nelle finestre di registrazione e accesso c'è il campo **Chiave di accesso** (facoltativo).
  - **Chiave giusta** (registrazione o accesso) → l'account diventa **amministratore permanente**: anche agli accessi
    successivi, senza più la chiave. Funziona anche da remoto.
  - **Chiave errata** → operazione rifiutata, nessun account creato, nessuna sessione. Si controlla solo a password corretta.
  - **5 chiavi errate** dallo stesso indirizzo (o sullo stesso account) → la **chiave** resta bloccata per 5 minuti
    (errore 429 con il tempo residuo; l'app mostra il conto alla rovescia). **Il server non si ferma**: accesso normale,
    file e altri utenti funzionano; anche la chiave giusta è rifiutata durante la pausa.
  - Chiave vuota → comportamento normale. Nessuna chiave configurata → ogni chiave è rifiutata.
- **La chiave non è nel codice.** Il server la legge, in ordine, da: variabile `AM_ADMIN_KEY`, file `server/admin_key.txt`,
  file `<cartella dati>/admin_key.txt`. Il file contiene solo la chiave (oppure `sha256:<hex>`, creato con `hash-key`, così
  sul server resta solo l'impronta). Nessuno può leggerla scaricando il codice **se il file non è su git**:
  - oggi `server/admin_key.txt` contiene la chiave provvisoria; nel `.gitignore` la riga `server/admin_key.txt` è
    **commentata**: **decommentala** quando il progetto va sul server/su git (e se il file era già stato committato:
    `git rm --cached server/admin_key.txt`). Se è già finito su git, considera la chiave compromessa e cambiala.
  - sul server metti una chiave **lunga** (almeno 16 caratteri casuali, meglio con `hash-key`): 5 tentativi ogni 5 minuti
    per indirizzo non proteggono da una chiave corta provata da molti indirizzi.
  - `python -m server serve` avvisa se la chiave è corta o disattivata.

## HTTPS (consigliato; obbligatorio fuori dalla rete locale)
Il server parla HTTP: le password non devono viaggiare in chiaro. Metti davanti un proxy con certificato, ad esempio Caddy:
```
server.tuodominio.it {
    request_body { max_size 4GB }
    reverse_proxy 127.0.0.1:8765
}
```
Avvia il server con `--host 127.0.0.1 --trust-proxy` (senza `--trust-proxy` tutti gli utenti sembrerebbero avere l'IP del
proxy e dividerebbero lo stesso blocco della chiave). Gli utenti inseriscono `https://server.tuodominio.it` nell'app.

## Avvio automatico (Linux, systemd) — `/etc/systemd/system/analisi-server.service`
```
[Unit]
Description=Server Analisi Metrologica
After=network.target
[Service]
WorkingDirectory=/opt/analisi
Environment=AM_ADMIN_KEY=...la-tua-chiave-lunga...
ExecStart=/usr/bin/python3 -m server --data /opt/analisi/datasets/server_data serve --host 127.0.0.1 --port 8765 --trust-proxy
Restart=always
User=analisi
[Install]
WantedBy=multi-user.target
```
`systemctl enable --now analisi-server`

## Regole delle cartelle

| | Utente | Amministratore |
|---|---|---|
| Leggere/scaricare foto, modelli, dataset | sì | sì |
| Inserire file e cartelle | sì, **senza sovrascrivere** | sì |
| Caricare modelli YOLO | in `store/pending/models/<utente>/` (quarantena) | in quarantena, approvazione automatica |
| Caricare foto di una specie | foto, foto stereo o video in `store/pending/<area>/<utente>/`, poi "Invia per revisione" | come l'utente, ma l'invio è approvato subito |
| Approvare o rifiutare le foto inviate | no | sì |
| Rinominare, spostare, eliminare, approvare | no | sì |
| **Cartella personale** (`mine`) | solo la propria: legge, scrive, sovrascrive, sposta, elimina, entro la quota | solo la propria |
| Utenti, quota, registro attività | no | sì |

Quarantena: un `.pt` è un archivio pickle e può eseguire codice quando viene caricato; per questo i modelli degli utenti
non sono scaricabili dagli altri finché un amministratore non li approva. Nella cartella personale i modelli sono privati,
quindi senza quarantena. Quota predefinita 1024 MB per utente (`DEFAULT_QUOTA_MB` in `server/params.py`, modificabile per
utente dalla gestione utenti). Estensioni e dimensioni massime per area: `server/params.py`.

- Gli utenti non creano cartelle a mano in quest'area: la struttura nasce dal percorso del file che caricano
  (`Pinna nobilis/lx/img1.jpg`).

## Sicurezza in breve
- Password PBKDF2-SHA256 (240.000 iterazioni); token casuali salvati solo come hash, scadenza 30 giorni.
- Blocco dell'account per 5 minuti dopo 5 password errate; chiave confrontata a tempo costante.
- Disattivando un utente o cambiando la sua password le sue sessioni decadono; deve restare almeno un amministratore.
- Percorsi normalizzati (niente `..`, nomi riservati, collegamenti simbolici ignorati); estensioni e contenuto immagini verificati.
- Gli errori sono testi inglesi con chiave/parametri: l'app li traduce nella lingua dell'utente.
- Limite di richieste: 600 al minuto per indirizzo (`--rate-limit`); in più i blocchi su password e chiave. Per un server
  pubblico aggiungi anche la limitazione del proxy (Caddy/nginx). I permessi sono applicati dal server; i pulsanti nascosti nell'app sono solo comodità.
