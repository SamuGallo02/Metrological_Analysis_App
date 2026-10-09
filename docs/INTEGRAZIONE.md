# Integrazione nell'applicativo (da fare con il PC collegato)

Tutto è scritto e provato: **60 test** (server, client, sessione, chiave, quota, profilo, lingue, isolamento tra
pagine, finestre in modalità offscreen). Mancano solo i collegamenti con `main.py` e `gui/home_gui.py`, che non posso
fare senza vedere il tuo PC.

## 1. Struttura: una cartella per pagina

```
common/      condiviso: params.py (nomi, lingue, ruoli, aree, campi profilo), i18n, impostazioni, sicurezza, errori, Qt utils
  ui/language.py      selettore/scaricamento lingue
users/       pagina Utenti (client): params, api, session, store  +  ui/{login, account_bar, browser, transfer, profile, admin}
server/      server HTTP (nessuna dipendenza grafica): params, config (chiave), throttle, db, storage, app, __main__
analysis/    pagina Analisi: params (le 4 analisi), hub.py
training/    params, setup_dialog.py (avviso + installazione estensioni)   <- la tua training/page.py resta com'è
manual/      content.py (manuale inglese), page.py (visualizzatore)
tools/       extract_strings, build_language_packs, translations/<lingua>.py   (non vanno nell'app dell'utente)
installer/   runner.py (+ patch) con --prefetch
site/locales pacchetti lingua pronti da pubblicare sul sito
tests/ docs/
```
Regole (verificate da `tests/test_isolation.py`): ogni cartella importa **solo** `common` e se stessa
(`training` anche `core`/`installer`, l'ambiente dell'app); nessuna pagina importa un'altra; il server non importa Qt;
logica (api/session/store/db/storage) separata dalle finestre. Impostazioni e formati condivisi: tutti in
`common/params.py`; quelli propri di una pagina nel suo `params.py`. Così puoi lavorare su una pagina senza toccare le altre.

## 2. File da copiare nel progetto
Copia le cartelle `common/ users/ server/ analysis/ manual/ tools/ tests/ docs/` così come sono.
`training/`: aggiungi `params.py` e `setup_dialog.py` (non sovrascrivere il tuo `training/__init__.py` se ne ha uno).
`installer/runner.py`: sostituisce il tuo solo se non è diverso — in caso contrario applica `runner_prefetch.patch`.
`.gitignore`: aggiungi le righe di `.gitignore.snippet`.
Nell'installatore (download dell'app sul computer dell'utente) escludi `server/`, `tools/`, `tests/`, `docs/`, `site/`.

## 3. `main.py`
```python
from common.i18n import init_language
from users.session import Session
from users.ui import LoginDialog

init_language()                              # applica la lingua scelta (inglese se nessuna)
session = Session()
if not session.resume():                     # token valido, o server offline con sessione precedente
    dlg = LoginDialog(session)
    if not dlg.exec():
        sys.exit(0)                          # dlg.mode: "online" | "offline" | "guest"
window = HomeWindow(session=session)
```

## 4. `gui/home_gui.py`
1. **Barra account** in cima: `bar = AccountBar(session)`; `bar.profile_requested` → apri `ProfilePage(session)` nello stack;
   `bar.logout_requested` → `session.logout()`, chiudi e rilancia l'accesso.
2. **Rimuovi i pulsanti Foto e Video**. Un solo pulsante **Analisi** → `AnalysisHub(demo=<il tuo widget demo>)` nello stack.
   La demo compare solo lì. Collega `hub.requested` agli id (provvisori, in `analysis/params.py`):
   `photo, photo_stereo, video, video_stereo` → le pagine che oggi aprono Foto/Video/Stereo. **Da verificare: nomi e
   descrizioni delle 4 analisi.**
3. Home **utente**: la home attuale + scheda **Server** (`ServerBrowserDialog(session)`), **Training**, **Manuale**
   (`ManualWidget()`), **Profilo**.
4. Home **server** (`session.is_admin`): `AdminHome(session, on_training=..., on_analysis=<apri l'hub>)` come pagina iniziale.
5. **Train**: `from training.setup_dialog import ensure_training_ready` →
   `if ensure_training_ready(self): self.stack.setCurrentIndex(IDX_TRAINING)`; togli il `showEvent`/`prompt_if_needed`
   di `training/page.py` (ora è nel pulsante).
6. Le cartelle locali scelte nel profilo: `session.local_folders()` → `{"photos","models","datasets","results"}`;
   usale al posto dei percorsi fissi dell'app. `ProfilePage.folders_changed` segnala la modifica.

## 5. Lingue
- Il codice usa `tr("Testo inglese")`: il testo inglese **è** la chiave. Le tue pagine esistenti hanno ancora stringhe
  italiane: da convertire in inglese + `tr()` (lo faccio quando il PC è collegato, pagina per pagina). Finché non è fatto,
  le nuove finestre sono tradotte e le vecchie restano in italiano.
- Per aggiungere/modificare testi: `python -m tools.extract_strings` (elenco), aggiorna
  `tools/translations/<lingua>.py`, aumenta `VERSION`, poi `python -m tools.build_language_packs --out site/locales`
  (controlla copertura, segnaposto, manuale) e pubblica la cartella.
- **Sito**: copia `site/locales/` nel repo `Nautilus_Website` (diventa `.../Nautilus_Website/locales/index.json`, già
  l'indirizzo in `common/params.py`). Il file `index.json` contiene versione, dimensione e SHA-256 di ogni lingua; l'app
  verifica l'impronta e propone gli aggiornamenti. Se cambi il sito, aggiorna `SITE_URL`.
- L'inglese è preinstallato; it, es, de, fr, zh, ja si scaricano da *Profilo → Lingua* e restano disponibili offline.
  La lingua cambia al riavvio. Traduzioni scritte da me: fai rileggere i testi a un madrelingua prima di pubblicarli.

## 6. Cosa verificare domani
- Nomi e descrizioni delle 4 analisi (`analysis/params.py`) e il widget demo da passare all'hub.
- Il **manuale** (`manual/content.py`) descrive l'app in modo generale: correggi i passaggi dell'analisi con i nomi reali
  dei pulsanti; poi aggiorna le 6 traduzioni (`tools/translations/`) e ripubblica.
- Che `core.environment_manager` esponga `get_cuda_status`, `launch_training_installer`, `PROJECT_ROOT` (usati da
  `training/setup_dialog.py`).
- Il problema ancora aperto dell'installazione: gli import (`cv2, numpy, pandas, torch, ultralytics`) falliscono nel venv;
  mandami le ultime righe di `install_log.txt`.
