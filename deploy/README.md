# Messa online del server

Il server usa solo la libreria standard di Python (3.10+). Tutti i comandi si lanciano dalla cartella del progetto.

## 1. Test su altri dispositivi (stessa rete Wi-Fi/LAN)
Su Windows basta fare doppio clic su `deploy\windows\avvia_server_test.cmd`. Equivale a:
```
python -m server create-admin NOME        # solo la prima volta
python -m server serve --lan              # = --host 0.0.0.0
```
All'avvio il server stampa gli indirizzi da usare (es. `http://192.168.1.20:8765`). Comando utile in qualsiasi momento: `python -m server lan`.

- **Firewall di Windows**: la prima volta esegui `deploy\windows\open_firewall.cmd` *come amministratore* (apre la porta 8765 solo
  sulle reti private). A fine test: `close_firewall.cmd`.
- **Prova rapida**: dal telefono apri `http://INDIRIZZO:8765/api/health`: deve rispondere `{"ok": true, ...}`.
- **App sull'altro dispositivo**: avviala con l'indirizzo del server:
  - Windows: `set AM_SERVER_URL=http://192.168.1.20:8765 && python main.py`
  - macOS/Linux: `AM_SERVER_URL=http://192.168.1.20:8765 python3 main.py`
- Se non risponde: il Wi-Fi "ospiti" spesso isola i dispositivi; l'IP del PC può cambiare (riesegui `python -m server lan`).
- Fuori da una rete di casa/ufficio le password viaggiano in chiaro (HTTP): usa il punto 2 o 3.

**Sicurezza durante il test.** Con il server raggiungibile dalla rete, una chiave di accesso amministratore più corta di 16 caratteri
viene **disattivata automaticamente per quell'avvio** (gli amministratori creati con `create-admin` funzionano normalmente).
Per tenerla comunque: `--allow-weak-key` (solo su una rete di cui ti fidi). Il server limita inoltre a 600 richieste/minuto
per indirizzo (`--rate-limit N`, `0` = nessun limite).

## 2. Accesso temporaneo da Internet, con HTTPS (nessuna porta da aprire sul router)
Con un tunnel il PC resta dietro il router e ottieni un indirizzo `https://…` valido finché il tunnel è acceso.
Con **cloudflared** (gratuito, senza account per i tunnel rapidi):
```
python -m server serve                                 # in un terminale (solo locale)
cloudflared tunnel --url http://127.0.0.1:8765         # in un altro: stampa https://qualcosa.trycloudflare.com
```
Sugli altri dispositivi: `AM_SERVER_URL=https://qualcosa.trycloudflare.com`. L'indirizzo cambia a ogni avvio; chiudendo il
tunnel l'accesso termina. (Alternativa equivalente: `ngrok http 8765`.) Per un tunnel avvia il server con `python -m server serve --public` (equivale a `--trust-proxy` e applica le stesse regole di sicurezza di `--lan`: chiave corta disattivata).

## 3. Server stabile (Linux, VPS o Raspberry)
**Con Docker** (server + HTTPS automatico con Caddy):
```
# 1) metti il tuo dominio in deploy/Caddyfile
# 2) chiave amministratore lunga (opzionale):
export AM_ADMIN_KEY="$(openssl rand -hex 24)"
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml exec server python -m server --data /data create-admin NOME
```
**Senza Docker (systemd)**: copia il progetto in `/opt/analisi`, poi `deploy/analisi-server.service` e
`deploy/analisi-backup.{service,timer}` in `/etc/systemd/system/` e `systemctl enable --now analisi-server analisi-backup.timer`.
Metti davanti Caddy/nginx (vedi `deploy/Caddyfile`) e avvia il server con `--host 127.0.0.1 --trust-proxy`.

## Comandi di gestione
| Comando | Cosa fa |
|---|---|
| `python -m server doctor` | controlla Python, cartella dati, database, amministratori, chiave, disco, porta, backup |
| `python -m server status [--json]` | utenti, sessioni, attività 24 h, dimensioni delle cartelle, spazio libero (anche a server fermo) |
| `python -m server backup [--files] [--keep N]` | copia coerente del database (anche a server acceso); `--files` aggiunge un `.tar.gz` di tutti i dati; ruota gli ultimi N |
| `python -m server backups` / `restore FILE` | elenca / ripristina il database (server fermo; il precedente resta come `.before-restore`) |
| `python -m server users list \| passwd \| disable \| enable \| unlock NOME` | gestione account senza l'app (password dimenticata, account bloccato) |
| `python -m server lan` | indirizzi e comandi da usare sugli altri dispositivi |

Dal server in esecuzione: `GET /api/health` (pubblico, per i controlli di stato; include `uptime`) e `GET /api/stats`
(solo amministratori: stesse informazioni di `status` più il numero di richieste servite).
Il registro è in `<dati>/logs/server.log` (rotazione automatica, 5 file da 5 MB).

## Integrazione continua
`.github/workflows/tests.yml` esegue i test del server su Python 3.10 e 3.12 e verifica che l'immagine Docker si costruisca,
a ogni push su GitHub.
