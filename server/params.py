"""Parametri del server (limiti, tempi, estensioni). Un solo posto da modificare."""
from common.params import PROFILE_FIELDS  # noqa: F401  (definiti in common: li usa anche il client)

API_VERSION = 1
DEFAULT_PORT = 8765

TOKEN_TTL = 30 * 24 * 3600           # durata di una sessione
LOGIN_MAX_FAILS = 5                  # password errate prima del blocco dell'account
LOGIN_LOCK_SECONDS = 300
KEY_MAX_FAILS = 5                    # chiavi amministratore errate prima del blocco (solo l'uso della chiave)
KEY_LOCK_SECONDS = 300

MAX_JSON = 1 << 20
DEFAULT_QUOTA_MB = 1024              # cartella personale ("mine") di ogni utente

EXTENSIONS = {
    "photos": {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"},
    "models": {".pt", ".onnx"},
    "datasets": {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".txt", ".yaml", ".yml",
                 ".json", ".csv", ".zip"},
}
EXTENSIONS["mine"] = EXTENSIONS["datasets"] | EXTENSIONS["models"] | {".pdf", ".md", ".xlsx", ".docx", ".mp4", ".avi", ".mov"}
MAX_BYTES = {"photos": 64 << 20, "models": 2 << 30, "datasets": 4 << 30, "mine": 4 << 30}

PENDING = "_pending"                 # quarantena dei modelli caricati dagli utenti (dentro models/)
TMP = ".uploads_tmp"

ADMIN_KEY_FILES = ("admin_key.txt",)  # cercati in server/ e nella cartella dei dati; mai nel codice
