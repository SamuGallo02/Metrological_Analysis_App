"""Server parameters (limits, times, extensions). A single place to edit."""
from common.params import (LOCAL_FOLDER_NAMES, PROFILE_FIELDS, SPECIES_EXAMPLE, SPECIES_RE,
                            SUBMISSION_APPROVED, SUBMISSION_PENDING, SUBMISSION_REJECTED, SUBMISSION_STATUSES)  # noqa: F401  (defined in common: also used by the client)

API_VERSION = 1
DEFAULT_PORT = 8765

TOKEN_TTL = 30 * 24 * 3600           # session duration
LOGIN_MAX_FAILS = 5                  # wrong passwords before the account is locked
LOGIN_LOCK_SECONDS = 300
KEY_MAX_FAILS = 5                    # wrong admin keys before lockout (key use only)
KEY_LOCK_SECONDS = 300

RATE_LIMIT_PER_MIN = 600             # requests per minute per address (0 = unlimited); stops floods, not normal use
MAX_JSON = 1 << 20
DEFAULT_QUOTA_MB = 1024              # personal folder ("mine") of each user

EXTENSIONS = {
    "photos": {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"},
    "models": {".pt", ".onnx", ".json"},
    "datasets": {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".txt", ".yaml", ".yml",
                 ".json", ".csv", ".zip"},
}
EXTENSIONS["mine"] = EXTENSIONS["datasets"] | EXTENSIONS["models"] | {".pdf", ".md", ".xlsx", ".docx", ".mp4", ".avi", ".mov"}
EXTENSIONS["species"] = EXTENSIONS["photos"]
MAX_BYTES = {"photos": 64 << 20, "models": 2 << 30, "datasets": 4 << 30, "mine": 4 << 30, "species": 64 << 20}
MAX_BYTES_EXT = {("models", ".json"): 1 << 20}      # i metadati dei modelli sono piccoli: 1 MB

# Server area -> folder name inside the data folder. They are the same names as the local folders
# (common.params.LOCAL_FOLDER_NAMES), so that on the machine hosting the server the server data and the local data
# of the app are one and the same folder.
AREA_DIRS = {"photos": LOCAL_FOLDER_NAMES["photo_stereo"], "models": LOCAL_FOLDER_NAMES["models"],
             "datasets": LOCAL_FOLDER_NAMES["training"], "mine": LOCAL_FOLDER_NAMES["users"],
             "species": LOCAL_FOLDER_NAMES["species"]}

PENDING = "_pending"                 # quarantine for models uploaded by users (inside models/)
TMP = ".uploads_tmp"

KIND_PHOTOS, KIND_DATASET, KIND_MODEL = "photos", "dataset", "model"      # what a submission is about

ADMIN_KEY_FILES = ("admin_key.txt",)  # searched in server/ and in the data folder; never in the code

# Photos of a species: <Genus species>/FOTO/<image>
#                      <Genus species>/FOTO STEREO/<rx|lx>/<image>

SPECIES_SIDES = ("rx", "lx")
SPECIES_IMAGE_EXT = EXTENSIONS["photos"]
SPECIES_MONO_EXAMPLE = f"{SPECIES_EXAMPLE}/image.jpg"
SPECIES_STEREO_EXAMPLE = f"{SPECIES_EXAMPLE}/{SPECIES_SIDES[0]}/image.jpg"
DATASET_EXAMPLE = "my_dataset/images/img_01.jpg"
