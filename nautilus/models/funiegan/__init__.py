"""FUnIE-GAN: a small, fast GAN for underwater colour correction (Islam et al., 2020)."""

import os

import cv2
import numpy as np

from nautilus import WEIGHTS_DIR, Param, register
from nautilus.inference import Network, from_nchw, to_nchw

from .net import GeneratorFunieGAN

WEIGHTS_URL = "https://raw.githubusercontent.com/xahidbuffon/FUnIE-GAN/master/PyTorch/models/funie_generator.pth"

network = Network(os.path.join(WEIGHTS_DIR, "funie_gan.pth"), GeneratorFunieGAN, WEIGHTS_URL)

# Long side of the image given to the network; None = 256x256 as in training, 0 = full size.
SIZES = {
    "Standard (fastest)": None,
    "Medium (512 px)": 512,
    "Large (1024 px)": 1024,
    "Full size (slowest)": 0,
}


def _network_size(h, w, size):
    """Size (w, h) the image is resized to before the network; sides are multiples of 32."""
    if size is None:
        return 256, 256
    scale = 1 if size == 0 else min(1, size / max(h, w))
    return max(32, round(w * scale / 32) * 32), max(32, round(h * scale / 32) * 32)


def _generate(rgb):
    out = network(to_nchw(rgb) * 2 - 1)  # the network works in [-1, 1]
    return from_nchw((out + 1) / 2)


@register(
    id="funiegan",
    name="Vivid colour, fast",
    technical="FUnIE-GAN neural network (Islam et al., IEEE RA-L 2020), trained on the EUVP dataset",
    kind="deep",
    description=(
        "Warmer, brighter, more saturated colours from a small and fast neural network. "
        "Good for a quick look through many photos and for presentation pictures. It can "
        "exaggerate colours or add texture that isn't there, so don't use it for colour measurements."
    ),
    params=[
        Param("size", "Processing size", "Standard (fastest)", type="choice", choices=list(SIZES),
              help="The network learned on small 256-pixel pictures. Larger sizes can keep finer "
                   "structures but are slower and may look less natural."),
        Param("detail_transfer", "Keep full sharpness", True, type="bool",
              help="Apply the colour change to your full-size photo, so no detail is lost. Recommended."),
        Param("strength", "Strength", 1.0, min=0, max=1, step=0.05,
              help="0 = original photo, 1 = full effect."),
    ],
    order=10,
    check=network.check,
    preload=network.load,
)
def funiegan(image, size, detail_transfer, strength):
    h, w = image.shape[:2]
    rgb = image[:, :, ::-1]
    net_w, net_h = _network_size(h, w, SIZES[size])
    small = cv2.resize(rgb, (net_w, net_h), interpolation=cv2.INTER_AREA)
    out_small = _generate(small)

    if detail_transfer:
        # Upsample only the change the network made, and add it to the sharp original.
        delta = out_small.astype(np.float32) - small.astype(np.float32)
        delta = cv2.resize(delta, (w, h), interpolation=cv2.INTER_LINEAR)
    else:
        out = cv2.resize(out_small, (w, h), interpolation=cv2.INTER_CUBIC)
        delta = out.astype(np.float32) - rgb.astype(np.float32)

    result = np.clip(rgb.astype(np.float32) + strength * delta, 0, 255).astype(np.uint8)
    return result[:, :, ::-1].copy()
