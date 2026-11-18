"""Parameters of the web application (one place to edit)."""
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent / "static"
JOBS_DIR = "web_jobs"                     # inside the server's data folder: results of the analyses (overlays, csv)

JOB_KEEP_SECONDS = 24 * 3600              # finished analyses are deleted after this time
JOBS_PER_USER = 20                        # finished analyses kept per user (the oldest are deleted)
MAX_PAIRS = 2000                          # stereo pairs analysed in one job
OVERLAY_MAX_SIDE = 1600                   # the overlay images are reduced to this size (pixels) before being sent
OVERLAY_JPEG_QUALITY = 85

MODEL_SUFFIXES = (".pt", ".onnx")
STEREO_DEFAULT = {"baseline_mm": 60.0, "focal_length_px": 1400.0}
STEREO_LIMITS = {"baseline_mm": (1.0, 5000.0), "focal_length_px": (10.0, 100000.0)}

LANGUAGES = ("en", "it", "es", "de", "fr", "zh", "ja")

CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
                 ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}

# The pages load only their own files; images are shown from blob: URLs created by the page itself.
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; "
                               "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}
