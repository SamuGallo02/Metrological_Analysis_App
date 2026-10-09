"""Parametri globali dell'applicazione (nomi, lingue, indirizzi). Un solo posto da modificare."""

APP_NAME = "Metrological Analysis"
DATA_DIR_NAME = "AnalisiMetrologica"          # cartella dei dati dell'utente (impostazioni, lingue, sessione)

DEFAULT_LANGUAGE = "en"                        # lingua base, l'unica preinstallata
# codice -> (nome in inglese, nome nella lingua stessa)
LANGUAGES = {
    "en": ("English", "English"),
    "it": ("Italian", "Italiano"),
    "es": ("Spanish", "Español"),
    "de": ("German", "Deutsch"),
    "fr": ("French", "Français"),
    "zh": ("Chinese (Mandarin)", "中文（普通话）"),
    "ja": ("Japanese", "日本語"),
}

DEFAULT_SERVER_URL = ""                        # indirizzo del server proposto al primo accesso (poi si ricorda l'ultimo usato)
SITE_URL = "https://samugallo02.github.io/Nautilus_Website/"
LANG_INDEX_URL = SITE_URL + "locales/index.json"     # elenco dei pacchetti lingua scaricabili

NET_TIMEOUT = 20.0                             # secondi
CHUNK = 1 << 20                                # byte per blocco nei trasferimenti


# ---- ruoli e aree: condivisi da server e client (un solo posto) ----------------------------------------------
ROLE_USER = "user"                             # vista classica
ROLE_SERVER = "server"                         # amministratore: utenti, database, training
ROLES = (ROLE_USER, ROLE_SERVER)

AREAS_SHARED = ("photos", "models", "datasets")    # cartelle comuni: tutti leggono e inseriscono, l'admin modifica
AREA_MINE = "mine"                                  # cartella personale sul server: il proprietario fa tutto
AREAS = AREAS_SHARED + (AREA_MINE,)

# campi del profilo utente -> lunghezza massima (usati da server e client)
PROFILE_FIELDS = {"full_name": 80, "email": 120, "organization": 120, "phone": 40, "bio": 500}
