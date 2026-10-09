"""Parameters of the Analysis page: the available analyses and their colors.

`id` is what `AnalysisHub.requested` emits and what the application maps to the existing page.
"""
from common.i18n import N_

PHOTO_COLOR, VIDEO_COLOR = "#1565c0", "#6a1b9a"      # same colors as the home cards

# (id, title, description, color) - the texts are in English and are translated by the language packs
ANALYSES = (
    ("photo", N_("Photo analysis"), N_("Detection and segmentation on a single photo."), PHOTO_COLOR),
    ("photo_stereo", N_("Stereo photo analysis"),
     N_("Real measurements (length, width, distance) on left/right photo pairs."), PHOTO_COLOR),
    ("video", N_("Video analysis"), N_("Detection and tracking on a single video."), VIDEO_COLOR),
    ("video_stereo", N_("Stereo video analysis"), N_("Detection, tracking and real measurements on a stereo video."), VIDEO_COLOR),
)
CARD_MIN_SIZE = (280, 150)
MAX_WIDTH = 960                # maximum width of the central block
