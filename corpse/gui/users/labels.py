"""Translated labels for roles and areas (functions: the language may change after import)."""
from common.i18n import tr
from common.params import AREA_MINE, ROLE_SERVER, SUBMISSION_APPROVED, SUBMISSION_PENDING, SUBMISSION_REJECTED

PENDING_DIR = "_pending" 

def role_label(role: str) -> str:
    return tr("Server (administrator)") if role == ROLE_SERVER else tr("User")


def area_label(area: str) -> str:
    return {"photos": tr("Photos"), "stereo": tr("Stereo photos"), "videos": tr("Videos"), "stereo_videos": tr("Stereo videos"),
            "models": tr("YOLO models"), "datasets": tr("Datasets"), AREA_MINE: tr("My folder")}.get(area, area)


def status_label(status: str) -> str:
    return {SUBMISSION_PENDING: tr("Pending"), SUBMISSION_APPROVED: tr("Approved"),
            SUBMISSION_REJECTED: tr("Rejected")}.get(status, status)


def folder_label(name: str) -> str:
    """Readable name of a server folder: the internal quarantine folder is not shown as is."""
    return tr("Awaiting approval") if name == PENDING_DIR else name


def path_label(path: str) -> str:
    return " / ".join(folder_label(part) for part in path.split("/")) if path else ""
