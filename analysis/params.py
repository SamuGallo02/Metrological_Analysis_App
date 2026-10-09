"""Parametri della pagina Analisi: le analisi disponibili e i loro colori.

`id` e' cio' che `AnalysisHub.requested` emette e che l'applicazione collega alla pagina esistente.
"""
from common.i18n import N_

PHOTO_COLOR, VIDEO_COLOR = "#1565c0", "#6a1b9a"      # stessi colori delle schede della home

# (id, titolo, descrizione, colore) - i testi sono inglesi e vengono tradotti dai pacchetti lingua
ANALYSES = (
    ("photo", N_("Photo analysis"), N_("Detection and segmentation on a single photo."), PHOTO_COLOR),
    ("photo_stereo", N_("Stereo photo analysis"),
     N_("Real measurements (length, width, distance) on left/right photo pairs."), PHOTO_COLOR),
    ("video", N_("Video analysis"), N_("Detection and tracking on a single video."), VIDEO_COLOR),
    ("video_stereo", N_("Stereo video analysis"), N_("Detection, tracking and real measurements on a stereo video."), VIDEO_COLOR),
)
CARD_MIN_SIZE = (280, 150)
MAX_WIDTH = 960                # larghezza massima del blocco centrale
