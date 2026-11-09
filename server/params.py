"""Server parameters (limits, times, extensions). A single place to edit."""
from common.paths import LOCAL_DIR
from common.params import (AREAS_MEDIA, IMAGE_SUFFIXES, KIND_AREA, KIND_DATASET, KIND_MODEL, KIND_PHOTOS,  # noqa: F401
                           KIND_STEREO, KIND_VIDEO, KINDS_MEDIA, LABEL_SUFFIX, PROFILE_FIELDS, SPECIES_EXAMPLE,
                           SPECIES_RE, STEREO_SIDES, VIDEO_SUFFIXES,
                            SUBMISSION_APPROVED, SUBMISSION_PENDING, SUBMISSION_REJECTED, SUBMISSION_STATUSES)  # noqa: F401  (defined in common: also used by the client)

API_VERSION = 1
DEFAULT_PORT = 8765
DEFAULT_DATA_DIR = LOCAL_DIR.parent / "server_data"      # the server's own folder, apart from the app's local data

TOKEN_TTL = 30 * 24 * 3600           # session duration
LOGIN_MAX_FAILS = 5                  # wrong passwords before the account is locked
LOGIN_LOCK_SECONDS = 300
KEY_MAX_FAILS = 5                    # wrong admin keys before lockout (key use only)
KEY_LOCK_SECONDS = 300

RATE_LIMIT_PER_MIN = 600             # requests per minute per address (0 = unlimited); stops floods, not normal use
MAX_JSON = 1 << 20
DEFAULT_QUOTA_MB = 1024              # personal folder ("mine") of each user

_IMAGES, _VIDEOS = set(IMAGE_SUFFIXES), set(VIDEO_SUFFIXES)
EXTENSIONS = {
    "photos": _IMAGES | {LABEL_SUFFIX},                  # a label file (.txt) goes with its photo
    "stereo": _IMAGES | {LABEL_SUFFIX},
    "videos": _VIDEOS | {LABEL_SUFFIX},
    "models": {".pt", ".onnx", ".json"},
    "datasets": _IMAGES | {".txt", ".yaml", ".yml", ".json", ".csv", ".zip"},
}
EXTENSIONS["mine"] = EXTENSIONS["datasets"] | EXTENSIONS["models"] | _VIDEOS | {".pdf", ".md", ".xlsx", ".docx"}
MAX_BYTES = {"photos": 64 << 20, "stereo": 64 << 20, "videos": 4 << 30, "models": 2 << 30, "datasets": 4 << 30,
             "mine": 4 << 30}
MAX_BYTES_EXT = {("models", ".json"): 1 << 20,            # model metadata is small: 1 MB
                 ("photos", ".txt"): 1 << 20, ("stereo", ".txt"): 1 << 20, ("videos", ".txt"): 64 << 20}

# Layout of the data folder (nothing here depends on how the app shows the files):
#   store/library/<area>/...        approved items, one folder per kind
#   store/pending/<area>/<user>/... uploads waiting for review (moved to the library, or deleted, by the review)
#   store/mine/<user>/...           personal folders
# The logical path "_pending/..." of an area is what the API shows for its waiting uploads.
STORE_DIR, LIBRARY_DIR, PENDING_DIR_NAME, MINE_DIR = "store", "library", "pending", "mine"

PENDING = "_pending"                 # logical name of the waiting uploads inside an area (administrators only)
TMP = ".uploads_tmp"

ADMIN_KEY_FILES = ("admin_key.txt",)  # searched in server/ and in the data folder; never in the code

# What an upload of each media kind looks like (inside its area):
#   photos  <Genus species>/<image>[.txt label]          stereo  <Genus species>/<lx|rx>/<image>[.txt label]
#   videos  <Genus species>/<video>[.txt label]
SPECIES_IMAGE_EXT = _IMAGES
SPECIES_VIDEO_EXT = _VIDEOS
SPECIES_MONO_EXAMPLE = f"{SPECIES_EXAMPLE}/image.jpg"
SPECIES_STEREO_EXAMPLE = f"{SPECIES_EXAMPLE}/{STEREO_SIDES[0]}/image.jpg"
SPECIES_VIDEO_EXAMPLE = f"{SPECIES_EXAMPLE}/video.mp4"
DATASET_EXAMPLE = "my_dataset/images/img_01.jpg"
