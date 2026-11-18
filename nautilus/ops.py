"""Classical image operations shared by the enhancement models.

Every function takes and returns an OpenCV-style BGR ``uint8`` array.
"""

import cv2
import numpy as np


# ------------------------------------------------------------------ contrast

def apply_CLAHE(image, clip_limit=2, tile_grid_size=(8, 8)):
    """Local contrast equalisation on the luminance channel only (colours are kept)."""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
    lab_eq = cv2.merge((clahe.apply(l), a, b))
    return cv2.cvtColor(lab_eq, cv2.COLOR_LAB2BGR)


def laplacian_sharpen(image, alpha=0.1):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_64F, ksize=3)
    lap_norm = cv2.normalize(lap, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    lap_colored = cv2.cvtColor(lap_norm, cv2.COLOR_GRAY2BGR)
    return cv2.addWeighted(image, 1.0, lap_colored, -alpha, 0)


# ------------------------------------------------------------------ colour

def stretch_channels(image, saturation=0.005):
    """Per-channel percentile stretch ("simplest colour balance").

    Same result as ``waternet.preprocess.white_balance_transform`` but vectorised,
    so it is fast enough to use on full-resolution images.
    """
    means = image.reshape(-1, 3).mean(axis=0) + 1e-6
    out = np.empty_like(image)
    for ch in range(3):
        # Channels with less energy (usually red underwater) are clipped more. A channel that is
        # almost empty (no red left at depth) would ask for more than all its pixels: cap it.
        s = min(saturation * means.max() / means[ch], 0.45)
        lo, hi = np.quantile(image[:, :, ch], [s, 1 - s])
        scaled = (image[:, :, ch].astype(np.float32) - lo) * (255.0 / max(hi - lo, 1e-6))
        out[:, :, ch] = np.clip(scaled, 0, 255).astype(np.uint8)
    return out


# ------------------------------------------------------------------ denoising

def median_blur(image, kernel=5):
    if kernel not in (3, 5, 7):
        raise ValueError("Median kernel must be 3, 5 or 7")
    return cv2.medianBlur(image, kernel)


def bilateral_filter(image):
    return cv2.bilateralFilter(image, d=9, sigmaColor=75, sigmaSpace=75)


def non_local_means(image):
    return cv2.fastNlMeansDenoisingColored(image, None, 10, 10, 7, 21)


# Labels are shown to users; the method is in brackets for reference.
DENOISERS = {
    "Off": lambda img: img,
    "Light (median)": median_blur,
    "Medium, keeps edges (bilateral)": bilateral_filter,
    "Strong, slow (non-local means)": non_local_means,
}
