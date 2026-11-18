"""WaterNet (Li et al., 2019) followed by the Nautilus post-processing.

This is the original Nautilus pipeline: WaterNet -> Laplacian sharpen -> CLAHE.
"""

import math
import os

import numpy as np

from nautilus import WEIGHTS_DIR, Param, register
from nautilus.inference import Network, from_nchw, to_nchw
from nautilus.ops import DENOISERS, apply_CLAHE, laplacian_sharpen

from .net import WaterNet
from .preprocess import transform

# WaterNet needs roughly 1.4 GB of RAM per megapixel (3.3 GB peak for 1920x1080), so larger
# images go through the network in tiles of at most this size.
MAX_MEGAPIXELS = float(os.environ.get("NAUTILUS_MAX_MEGAPIXELS", 8))
# Each output pixel depends only on the input within 13 px of it (the network's receptive
# field), so tiles that overlap by more than that give the same result as one pass.
TILE_MARGIN = 16

network = Network(os.path.join(WEIGHTS_DIR, "waternet.pt"), WaterNet)


def waternet(image_bgr):
    rgb = image_bgr[:, :, ::-1]
    # The colour transforms are global (whole-image statistics): compute them before tiling.
    wb, gc, he = transform(rgb)
    inputs = (rgb, wb, he, gc)
    h, w = rgb.shape[:2]
    side = int(math.sqrt(MAX_MEGAPIXELS * 1e6)) - 2 * TILE_MARGIN
    if h * w <= MAX_MEGAPIXELS * 1e6 or side < 64:
        return from_nchw(network(*(to_nchw(a) for a in inputs)))[:, :, ::-1].copy()
    out = np.empty((h, w, 3), np.uint8)
    for y in range(0, h, side):
        for x in range(0, w, side):
            y0, x0 = max(y - TILE_MARGIN, 0), max(x - TILE_MARGIN, 0)
            y1, x1 = min(y + side + TILE_MARGIN, h), min(x + side + TILE_MARGIN, w)
            tile = from_nchw(network(*(to_nchw(a[y0:y1, x0:x1]) for a in inputs)))
            th, tw = min(side, h - y), min(side, w - x)
            out[y:y + th, x:x + tw] = tile[y - y0:y - y0 + th, x - x0:x - x0 + tw]
    return out[:, :, ::-1].copy()


@register(
    id="waternet",
    name="Balanced colour & detail",
    technical="WaterNet neural network (Li et al., IEEE TIP 2019) + sharpening + CLAHE local contrast",
    kind="deep",
    description=(
        "Recommended starting point. A neural network trained on hundreds of underwater "
        "photos removes the green-blue cast and the haze, then fine detail and local contrast "
        "are gently boosted. The slowest method. Colours are the network's best estimate: "
        "check them against a colour reference if exact hues matter (e.g. for identification)."
    ),
    params=[
        Param("denoise", "Reduce grain first", "Off", type="choice", choices=list(DENOISERS),
              help="Smooths camera noise before the colours are corrected. Useful for dark, grainy footage."),
        Param("sharpen", "Sharpening", 0.1, min=0, max=0.5, step=0.01,
              help="Makes edges crisper. 0 turns it off. High values also sharpen the noise."),
        Param("clip_limit", "Local contrast", 2.0, min=0, max=6, step=0.1,
              help="Brings out detail in dark and bright areas. 0 turns it off; high values can look harsh."),
        Param("tile_size", "Local contrast regions", 8, type="int", min=2, max=32, step=1,
              help="The photo is split into this many regions per side for the local contrast. "
                   "More regions = more local adjustment."),
    ],
    order=0,
    check=network.check,
    preload=network.load,
)
def waternet_pipeline(image, denoise, sharpen, clip_limit, tile_size):
    image = DENOISERS[denoise](image)
    image = waternet(image)
    if sharpen > 0:
        image = laplacian_sharpen(image, alpha=sharpen)
    if clip_limit > 0:
        image = apply_CLAHE(image, clip_limit=clip_limit, tile_grid_size=(tile_size, tile_size))
    return image
