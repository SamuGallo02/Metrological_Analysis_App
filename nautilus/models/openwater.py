"""WaterNet for animals filmed against open water, without the milky veil.

Colour-correcting the whole frame turns empty water into a milky grey-blue veil, often with a
bright halo from the sun, lights or the camera housing. This method:

1. smooths the colour noise (not the detail): in very blue or green water the red channel
   holds only a few levels, which turn into coloured speckles once stretched;
2. runs WaterNet with gentler local contrast, which otherwise amplifies grain in empty water;
3. swaps the smooth large-scale light (haze, halo, light falloff) for an even water tone.
   Only the large-scale brightness changes, so the subject keeps WaterNet's colours.
"""

import cv2
import numpy as np

from nautilus import Param, register
from nautilus.models.waternet import network, waternet_pipeline
from nautilus.ops import DENOISERS

LUMA_BGR = np.array([0.114, 0.587, 0.299], np.float32)


def _guided_filter(guide, src, radius, eps=1e-3):
    """He et al. 2010: smooths ``src`` but keeps the edges of ``guide``."""
    size = (2 * radius + 1, 2 * radius + 1)
    mean = lambda x: cv2.boxFilter(x, -1, size)  # noqa: E731
    m_g, m_s = mean(guide), mean(src)
    a = (mean(guide * src) - m_g * m_s) / (mean(guide * guide) - m_g * m_g + eps)
    b = m_s - a * m_g
    return mean(a) * guide + mean(b)


def smooth_colour(image):
    """Smooth the colour channels only, guided by the brightness so colour edges stay put."""
    ycc = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb).astype(np.float32) / 255
    radius = max(4, round(max(image.shape[:2]) / 400))
    for c in (1, 2):
        ycc[..., c] = _guided_filter(ycc[..., 0], ycc[..., c], radius)
    return cv2.cvtColor(np.clip(ycc * 255 + 0.5, 0, 255).astype(np.uint8), cv2.COLOR_YCrCb2BGR)


def water_light(image, size=0.3):
    """Smooth estimate of the water's own light (haze, halo, light falloff), ignoring the subject.

    A median over 30% of the frame ignores anything smaller than about half of that window.
    """
    h, w = image.shape[:2]
    scale = min(1.0, 320 / max(h, w))
    small = cv2.resize(image, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
    k = max(3, int(max(small.shape[:2]) * size) | 1)
    light = cv2.medianBlur(small, k).astype(np.float32) / 255
    light = cv2.GaussianBlur(light, (0, 0), k / 4)
    return cv2.resize(light, (w, h), interpolation=cv2.INTER_CUBIC)


def remove_haze(image, strength=1.0, brightness=0.22, colour=1.0):
    """Replace the large-scale light with an even tone: the water's mean colour, at ``brightness``."""
    light = water_light(image)
    mean = light.reshape(-1, 3).mean(0)
    target = mean.mean() + colour * (mean - mean.mean())  # colour 0 = grey water
    target *= brightness / max(float(target @ LUMA_BGR), 1e-6)
    out = image.astype(np.float32) / 255 + strength * (target - light)
    return np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8)


@register(
    id="openwater",
    name="Clear open water",
    technical="WaterNet + colour-noise smoothing + haze and light-halo removal",
    kind="deep",
    description=(
        "For animals photographed against open water, with no seabed behind them. Removes the "
        "milky veil and the bright halo that colour correction leaves over empty water, so the "
        "subject stands out on an even, darker water background, and smooths the colour speckles "
        "of very blue or green water. Not meant for scenes with the seabed or a reef in view: "
        "large areas of it would be evened out like the haze."
    ),
    params=[
        Param("haze", "Remove haze", 1.0, min=0, max=1, step=0.05,
              help="Replaces the milky veil and bright halo over the water with an even tone. 0 turns it off."),
        Param("water_brightness", "Water brightness", 0.22, min=0.05, max=0.6, step=0.01,
              help="Brightness of the water once the haze is removed. Raise it if the result looks too dark."),
        Param("water_colour", "Water colour", 1.0, min=0, max=1.5, step=0.05,
              help="0 = grey water, 1 = the water's own tint after correction, above 1 = more tinted."),
        Param("clean_colour", "Smooth colour speckles", True, type="bool",
              help="Smooths colour noise before correcting (the detail is kept). Recommended in very "
                   "blue or green water, where it otherwise turns into coloured speckles."),
        Param("denoise", "Reduce grain first", "Off", type="choice", choices=list(DENOISERS),
              help="Smooths camera noise before the colours are corrected. Useful for dark, grainy footage."),
        Param("clip_limit", "Local contrast", 0.8, min=0, max=6, step=0.1,
              help="Brings out detail in dark and bright areas, but also the grain in empty water. 0 turns it off."),
        Param("sharpen", "Sharpening", 0.0, min=0, max=0.5, step=0.01,
              help="Makes edges crisper. 0 turns it off. High values also sharpen the noise."),
    ],
    order=5,
    check=network.check,
    preload=network.load,
)
def openwater(image, haze, water_brightness, water_colour, clean_colour, denoise, clip_limit, sharpen):
    if clean_colour:
        image = smooth_colour(image)
    image = waternet_pipeline(image, denoise=denoise, sharpen=sharpen, clip_limit=clip_limit, tile_size=8)
    if haze > 0:
        image = remove_haze(image, haze, water_brightness, water_colour)
    return image
