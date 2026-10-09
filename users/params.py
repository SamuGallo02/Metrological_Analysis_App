"""Parametri della pagina Utenti."""
from common.params import ROLE_SERVER, ROLE_USER

# permessi per ruolo (le operazioni sul server richiedono anche la rete: vedi Session.can)
PERMISSIONS = {
    "files.read": (ROLE_USER, ROLE_SERVER),
    "files.insert": (ROLE_USER, ROLE_SERVER),
    "files.modify": (ROLE_SERVER,),
    "files.delete": (ROLE_SERVER,),
    "models.approve": (ROLE_SERVER,),
    "users.manage": (ROLE_SERVER,),
    "training.manage": (ROLE_SERVER,),
    "training.run": (ROLE_USER, ROLE_SERVER),
    "analysis.run": (ROLE_USER, ROLE_SERVER),
    "mine.manage": (ROLE_USER, ROLE_SERVER),          # cartella personale sul server
}
SERVER_SIDE_PREFIXES = ("files.", "models.", "users.", "mine.")

# cartelle locali che l'utente puo' scegliere dal profilo: chiave -> (etichetta inglese)
LOCAL_FOLDERS = ("photos", "models", "datasets", "results")

# file nella cartella dei dati dell'utente
F_USERS, F_SESSION, F_USERS_CACHE, F_PROFILES = "users.json", "session.json", "users_cache.json", "profiles.json"
