"""Etichette tradotte di ruoli e aree (funzioni: la lingua puo' cambiare dopo l'import)."""
from common.i18n import tr
from common.params import AREA_MINE, ROLE_SERVER


def role_label(role: str) -> str:
    return tr("Server (administrator)") if role == ROLE_SERVER else tr("User")


def area_label(area: str) -> str:
    return {"photos": tr("Photos"), "models": tr("YOLO models"), "datasets": tr("Datasets"),
            AREA_MINE: tr("My folder")}.get(area, area)
