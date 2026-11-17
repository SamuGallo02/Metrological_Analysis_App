"""Global application parameters (names, languages, addresses). A single place to edit."""
import os

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
    "species": "dataset_Specie",
}
VENV_PARENT = "librery"                                 # container of the virtual environments

NET_TIMEOUT = 20.0                             # seconds
GOODBYE_TIMEOUT = 2.0                          # saying goodbye to the server on sign-out: never make the user wait
CHUNK = 1 << 20                                # bytes per block in transfers


# Models are published in one folder per species, named after the scientific name: "Genus species" (+ subspecies).
SPECIES_RE = r"[A-Z][a-z]{2,}( [a-z]{2,}){1,2}"
SPECIES_EXAMPLE = "Pinna nobilis"

# ---- roles and areas: shared by server and client (a single place) -------------------------------------------
ROLE_USER = "user"                             # classic view
ROLE_SERVER = "server"                         # administrator: users, database, training
ROLES = (ROLE_USER, ROLE_SERVER)

# Server areas. Each approved item lives in `store/library/<area>/` and each upload waits in `store/pending/<area>/`
# until an administrator approves it. The folders are organised by kind, whatever the app shows.
AREA_PHOTOS, AREA_STEREO, AREA_VIDEOS = "photos", "stereo", "videos"
AREA_STEREO_VIDEOS = "stereo_videos"
AREAS_MEDIA = (AREA_PHOTOS, AREA_STEREO, AREA_VIDEOS, AREA_STEREO_VIDEOS)         # one folder per species, then one per approved upload
AREAS_SHARED = AREAS_MEDIA + ("models", "datasets")           # common folders: everyone reads and adds, the admin edits
# inside a group: whoever made it looks after it, and can promote the others
GROUP_ADMIN, GROUP_MEMBER = "admin", "member"
GROUP_ROLES = (GROUP_ADMIN, GROUP_MEMBER)
AREA_GROUPS = "groups"                                        # shared folder of a work group: its members only
AREA_MINE = "mine"                                            # personal folder on the server: the owner can do everything
AREAS = AREAS_SHARED + (AREA_GROUPS, AREA_MINE)

# what a submission is about -> the area that holds it once approved
KIND_PHOTOS, KIND_STEREO, KIND_VIDEO, KIND_DATASET, KIND_MODEL = "photos", "stereo", "video", "dataset", "model"
KIND_STEREO_VIDEO = "stereo_video"
KIND_AREA = {KIND_PHOTOS: AREA_PHOTOS, KIND_STEREO: AREA_STEREO, KIND_VIDEO: AREA_VIDEOS,
             KIND_STEREO_VIDEO: AREA_STEREO_VIDEOS,
             KIND_MODEL: "models", KIND_DATASET: "datasets"}
KINDS_MEDIA = (KIND_PHOTOS, KIND_STEREO, KIND_VIDEO, KIND_STEREO_VIDEO)
KINDS_STEREO = (KIND_STEREO, KIND_STEREO_VIDEO)           # <Species>/<lx|rx>/<file>
KINDS_VIDEO = (KIND_VIDEO, KIND_STEREO_VIDEO)             # the media are videos, not photos

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")
VIDEO_SUFFIXES = (".mp4", ".avi", ".mov", ".mkv", ".webm")
# training asked of the server: a worker with a GPU takes the jobs one at a time
JOB_QUEUED, JOB_RUNNING, JOB_DONE, JOB_FAILED, JOB_CANCELLED = "queued", "running", "done", "failed", "cancelled"
JOB_STATES = (JOB_QUEUED, JOB_RUNNING, JOB_DONE, JOB_FAILED, JOB_CANCELLED)
JOB_OPEN = (JOB_QUEUED, JOB_RUNNING)
ENHANCED_DIR = "enhanced"                                     # improved copy of a photo or video, beside the original
ORIGINALS_DIR = "originals"                                   # where the original goes when an improved copy takes its place
ENHANCE_INBOX = "improve"                                     # personal folder on the server where a file waits to be improved
LABEL_SUFFIX = ".txt"                                         # YOLO labels sit next to the media with the same name
STEREO_SIDES = ("lx", "rx")

# user profile fields -> maximum length (used by server and client)
PROFILE_FIELDS = {"full_name": 80, "email": 120, "organization": 120, "phone": 40, "bio": 500}

# ---- subprocesses on Windows: never show a console window ---------------------------------------------------------
NO_WINDOW = {"creationflags": 0x08000000} if os.name == "nt" else {}                 # CREATE_NO_WINDOW
DETACHED_HIDDEN = ({"creationflags": 0x00000008 | 0x00000200, "close_fds": True} if os.name == "nt"       # DETACHED_PROCESS | NEW_PROCESS_GROUP
                   else {"start_new_session": True, "close_fds": True, "stdout": -3, "stderr": -3})        # -3 = subprocess.DEVNULL

# lines the installer writes to stdout for the windows that show its progress: "@@PROGRESS <percent> <text>", "@@WARN <text>"
PROGRESS_PREFIX = "@@PROGRESS"
WARN_PREFIX = "@@WARN"

# review of the species photos sent by users
SUBMISSION_PENDING = "pending"
SUBMISSION_APPROVED = "approved"
SUBMISSION_REJECTED = "rejected"
SUBMISSION_STATUSES = (SUBMISSION_PENDING, SUBMISSION_APPROVED, SUBMISSION_REJECTED)
