"""Parameters of the Users page."""
from common.params import ROLE_SERVER, ROLE_USER

# permissions by role (server operations also require the network: see Session.can)
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
    "mine.manage": (ROLE_USER, ROLE_SERVER),          # personal folder on the server
}
SERVER_SIDE_PREFIXES = ("files.", "models.", "users.", "mine.")

# local folders the user can choose from the profile: key -> (English label)
LOCAL_FOLDERS = ("photos", "models", "datasets", "results")

# files in the user's data folder
F_USERS, F_SESSION, F_USERS_CACHE, F_PROFILES = "users.json", "session.json", "users_cache.json", "profiles.json"
