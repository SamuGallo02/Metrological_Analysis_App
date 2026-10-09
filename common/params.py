"""Global application parameters (names, languages, addresses). A single place to edit."""

APP_NAME = "Metrological Analysis"
DATA_DIR_NAME = "AnalisiMetrologica"          # user data folder (settings, languages, session)

DEFAULT_LANGUAGE = "en"                        # base language, the only one preinstalled
# code -> (English name, name in the language itself)
LANGUAGES = {
    "en": ("English", "English"),
    "it": ("Italian", "Italiano"),
    "es": ("Spanish", "Español"),
    "de": ("German", "Deutsch"),
    "fr": ("French", "Français"),
    "zh": ("Chinese (Mandarin)", "中文（普通话）"),
    "ja": ("Japanese", "日本語"),
}

# Address of the Nautilus laboratory server: the sign-in page connects to it by itself, the user never types it.
# Replace it with the real address before distributing the app (the AM_SERVER_URL environment variable overrides it).
DEFAULT_SERVER_URL = "http://127.0.0.1:8765"
SITE_URL = "https://samugallo02.github.io/Nautilus_Website/"
LANG_INDEX_URL = SITE_URL + "locales/index.json"     # list of downloadable language packs

# ---- data folders (relative to the project root; absolute paths are in common/paths) ---------------------------
LOCAL_DATA_PARTS = ("datasets", "Dataset_Locale")      # user local data
LOCAL_FOLDER_NAMES = {                                  # area -> folder name inside the local data
    "photo": "dataset_Foto", "photo_stereo": "dataset_Foto_Stereo",
    "video": "dataset_Video", "video_stereo": "dataset_Video_Stereo",
    "training": "dataset_Training", "models": "models", "results": "results", "runs": "runs",
    "users": "users",                                   # personal folders of the accounts (server area "mine")
}
VENV_PARENT = "librery"                                 # container of the virtual environments

NET_TIMEOUT = 20.0                             # seconds
CHUNK = 1 << 20                                # bytes per block in transfers


# Models are published in one folder per species, named after the scientific name: "Genus species" (+ subspecies).
SPECIES_RE = r"[A-Z][a-z]{2,}( [a-z]{2,}){1,2}"
SPECIES_EXAMPLE = "Pinna nobilis"

# ---- roles and areas: shared by server and client (a single place) -------------------------------------------
ROLE_USER = "user"                             # classic view
ROLE_SERVER = "server"                         # administrator: users, database, training
ROLES = (ROLE_USER, ROLE_SERVER)

AREAS_SHARED = ("photos", "models", "datasets")    # common folders: everyone reads and adds, the admin edits
AREA_MINE = "mine"                                  # personal folder on the server: the owner can do everything
AREAS = AREAS_SHARED + (AREA_MINE,)

# user profile fields -> maximum length (used by server and client)
PROFILE_FIELDS = {"full_name": 80, "email": 120, "organization": 120, "phone": 40, "bio": 500}
