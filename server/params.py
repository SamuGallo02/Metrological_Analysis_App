"""Server parameters (limits, times, extensions). A single place to edit."""
from common.params import LOCAL_FOLDER_NAMES, PROFILE_FIELDS, SPECIES_EXAMPLE, SPECIES_RE  # noqa: F401  (defined in common: also used by the client)

API_VERSION = 1
DEFAULT_PORT = 8765

TOKEN_TTL = 30 * 24 * 3600           # session duration
LOGIN_MAX_FAILS = 5                  # wrong passwords before the account is locked
LOGIN_LOCK_SECONDS = 300
KEY_MAX_FAILS = 5                    # wrong admin keys before lockout (key use only)
KEY_LOCK_SECONDS = 300

MAX_JSON = 1 << 20
DEFAULT_QUOTA_MB = 1024              # personal folder ("mine") of each user

EXTENSIONS = {
    "photos": {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"},
    "models": {".pt", ".onnx"},
    "datasets": {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".txt", ".yaml", ".yml",
                 ".json", ".csv", ".zip"},
}
EXTENSIONS["mine"] = EXTENSIONS["datasets"] | EXTENSIONS["models"] | {".pdf", ".md", ".xlsx", ".docx", ".mp4", ".avi", ".mov"}
MAX_BYTES = {"photos": 64 << 20, "models": 2 << 30, "datasets": 4 << 30, "mine": 4 << 30}

# Server area -> folder name inside the data folder. They are the same names as the local folders
# (common.params.LOCAL_FOLDER_NAMES), so that on the machine hosting the server the server data and the local data
# of the app are one and the same folder.
AREA_DIRS = {"photos": LOCAL_FOLDER_NAMES["photo_stereo"], "models": LOCAL_FOLDER_NAMES["models"],
             "datasets": LOCAL_FOLDER_NAMES["training"], "mine": LOCAL_FOLDER_NAMES["users"]}

PENDING = "_pending"                 # quarantine for models uploaded by users (inside models/)
TMP = ".uploads_tmp"

ADMIN_KEY_FILES = ("admin_key.txt",)  # searched in server/ and in the data folder; never in the code
