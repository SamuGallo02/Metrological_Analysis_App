"""Colour balance and multi-scale fusion (Ancuti et al., IEEE TIP 2018).

"Color Balance and Fusion for Underwater Image Enhancement", doi:10.1109/TIP.2017.2759252.
A classical (no training, no weights) method: compensate the red channel lost in water,
white-balance, then blend a gamma-corrected and a sharpened version of the result, using
per-pixel weights for local contrast, saliency and saturation.
"""

import cv2
import numpy as np

from nautilus import Param, register


def compensate(img, alpha, blue):
    """Add back some of the green channel into red (and optionally blue), where red is weak."""
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    mr, mg, mb = r.mean(), g.mean(), b.mean()
    out = img.copy()
    out[..., 0] = r + alpha * (mg - mr) * (1 - r) * g
    if blue:
        out[..., 2] = b + alpha * (mg - mb) * (1 - b) * g
    return np.clip(out, 0, 1)


def gray_world(img):
    means = img.reshape(-1, 3).mean(axis=0) + 1e-6
    return np.clip(img * (means.mean() / means), 0, 1).astype(np.float32)


def stretch_levels(img, clip=0.005):
    """Stretch all channels together so the image uses the full range (keeps the colour balance)."""
    lo, hi = np.quantile(img, [clip, 1 - clip])
    return np.clip((img - lo) / max(hi - lo, 1e-6), 0, 1).astype(np.float32)


def unsharp(img, sigma, amount):
    """Sharpened input. The paper uses (I + stretch(I - blur(I))) / 2, but that adds a
    constant grey offset which washes out dark footage, so a zero-centred mask is used."""
    return np.clip(img + amount * (img - cv2.GaussianBlur(img, (0, 0), sigma)), 0, 1)


def fusion_weight(img):
    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
    lum = lab[..., 0] / 100.0
    laplacian = np.abs(cv2.Laplacian(lum, cv2.CV_32F))
    blurred = cv2.GaussianBlur(lab, (5, 5), 0)
    saliency = np.linalg.norm(blurred - lab.reshape(-1, 3).mean(axis=0), axis=2) / 100.0
    saturation = np.sqrt(((img - lum[..., None]) ** 2).mean(axis=2))
    return laplacian + saliency + saturation


def gaussian_pyramid(img, levels):
    pyr = [img]
    for _ in range(levels - 1):
        pyr.append(cv2.pyrDown(pyr[-1]))
    return pyr


def laplacian_pyramid(img, levels):
    gauss = gaussian_pyramid(img, levels)
    pyr = []
    for fine, coarse in zip(gauss, gauss[1:]):
        size = (fine.shape[1], fine.shape[0])
        pyr.append(fine - cv2.pyrUp(coarse, dstsize=size))
    pyr.append(gauss[-1])
    return pyr


def multiscale_fusion(inputs, weights, levels):
    total = sum(weights) + 1e-6
    weights = [w / total for w in weights]
    fused = None
    for img, w in zip(inputs, weights):
        lap = laplacian_pyramid(img, levels)
        gw = gaussian_pyramid(w, levels)
        layers = [l * g[..., None] for l, g in zip(lap, gw)]
        fused = layers if fused is None else [a + b for a, b in zip(fused, layers)]
    out = fused[-1]
    for layer in reversed(fused[:-1]):
        out = cv2.pyrUp(out, dstsize=(layer.shape[1], layer.shape[0])) + layer
    return out


@register(
    id="fusion",
    name="Restore lost red",
    technical="Colour balance and multi-scale fusion (Ancuti et al., IEEE TIP 2018)",
    description=(
        "Uses the physics of light in water instead of AI: puts back the red light that water "
        "absorbs first, balances the colours, then blends a contrast-boosted and a sharpened "
        "version of the photo. Fast, and every step is a simple, documented adjustment, so it "
        "is a good choice when photos will be measured or compared scientifically."
    ),
    params=[
        Param("red", "Red recovery", 1.0, min=0, max=2.5, step=0.05,
              help="How much red to restore. Increase in deep or very blue water; "
                   "decrease if the photo turns pink."),
        Param("blue", "Also recover blue", False, type="bool",
              help="Turn on in green, murky water (lakes, plankton-rich water) where blue light is also lost."),
        Param("gamma", "Mid-tone depth", 1.3, min=0.5, max=3, step=0.05,
              help="Higher values make mid-tones darker and richer; lower values brighten them."),
        Param("auto_levels", "Auto brightness", True, type="bool",
              help="Stretches the brightness to use the full range. Helps dark, murky photos."),
        Param("sharpen", "Sharpening", 1.0, min=0, max=3, step=0.1,
              help="Makes edges crisper. 0 turns it off."),
        Param("sharpen_sigma", "Sharpening size", 3.0, min=0.5, max=15, step=0.5,
              help="Size of the details to sharpen, in pixels: small values sharpen fine texture, "
                   "large values bigger shapes."),
        Param("levels", "Blending smoothness", 5, type="int", min=1, max=8, step=1,
              help="How smoothly the two versions are blended. Increase if you see halos around objects."),
    ],
    order=20,
)
def fusion(image, red, blue, gamma, auto_levels, sharpen, sharpen_sigma, levels):
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    balanced = gray_world(compensate(rgb, red, blue))
    if auto_levels:
        balanced = stretch_levels(balanced)

    gamma_input = np.power(balanced, gamma)
    sharp_input = unsharp(balanced, sharpen_sigma, sharpen)
    inputs = [gamma_input, sharp_input]
    weights = [fusion_weight(i) for i in inputs]

    # Don't build pyramid levels smaller than a few pixels.
    levels = max(1, min(levels, int(np.log2(min(image.shape[:2]))) - 2))
    out = multiscale_fusion(inputs, weights, levels)
    out = (np.clip(out, 0, 1) * 255).astype(np.uint8)
    return cv2.cvtColor(out, cv2.COLOR_RGB2BGR)
