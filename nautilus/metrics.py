"""No-reference underwater image quality metrics, for comparing models.

Both metrics are "higher is better" and need no ground-truth image, but they are
only rough proxies for what a human would prefer: an over-saturated, noisy image
can score higher than a natural-looking one. Use them next to your own eyes.

Images are downscaled to ``SIZE`` pixels on the long side first, so scores are
comparable between images of different resolutions (and fast to compute).
Absolute values vary between published implementations; compare scores
computed by this module with each other, not with numbers from papers.
"""

import cv2
import numpy as np

SIZE = 512


def _prepare(image_bgr):
    h, w = image_bgr.shape[:2]
    scale = SIZE / max(h, w)
    if scale < 1:
        image_bgr = cv2.resize(image_bgr, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    return image_bgr


def uciqe(image_bgr):
    """Underwater Colour Image Quality Evaluation (Yang & Sowmya, 2015)."""
    lab = cv2.cvtColor(image_bgr.astype(np.float32) / 255, cv2.COLOR_BGR2LAB)
    l, a, b = lab[..., 0] / 100, lab[..., 1] / 100, lab[..., 2] / 100
    chroma = np.sqrt(a**2 + b**2)
    sigma_c = chroma.std()
    lo, hi = np.quantile(l, [0.01, 0.99])
    contrast_l = hi - lo
    saturation = (chroma / np.maximum(l, 1e-3))[l > 1e-3].mean() if (l > 1e-3).any() else 0.0
    return float(0.4680 * sigma_c + 0.2745 * contrast_l + 0.2576 * min(saturation, 1.0))


def _trimmed_stats(x, trim=0.1):
    x = np.sort(x.ravel())
    k = int(trim * x.size)
    x = x[k: x.size - k] if x.size > 2 * k else x
    return x.mean(), x.var()


def _blocks(channel, k):
    h, w = channel.shape
    h, w = h - h % k, w - w % k
    blocks = channel[:h, :w].reshape(h // k, k, w // k, k)
    return blocks.max(axis=(1, 3)), blocks.min(axis=(1, 3))


def _eme(channel, k=8):
    bmax, bmin = _blocks(channel, k)
    valid = (bmin > 0) & (bmax > 0)
    if not valid.any():
        return 0.0
    return float(2 / bmax.size * np.log(bmax[valid] / bmin[valid]).sum())


def _logamee(gray, k=8):
    bmax, bmin = _blocks(gray, k)
    top, bot = bmax - bmin, bmax + bmin
    valid = (top > 0) & (bot > 0)
    if not valid.any():
        return 0.0
    ratio = top[valid] / bot[valid]
    return float(-1 / bmax.size * (ratio * np.log(ratio)).sum())


def uiqm(image_bgr):
    """Underwater Image Quality Measure (Panetta et al., 2016): colourfulness, sharpness, contrast."""
    img = image_bgr.astype(np.float32)
    b, g, r = img[..., 0], img[..., 1], img[..., 2]

    mu_rg, var_rg = _trimmed_stats(r - g)
    mu_yb, var_yb = _trimmed_stats((r + g) / 2 - b)
    uicm = -0.0268 * np.hypot(mu_rg, mu_yb) + 0.1586 * np.sqrt(var_rg + var_yb)

    def edge(ch):
        mag = np.hypot(cv2.Sobel(ch, cv2.CV_32F, 1, 0), cv2.Sobel(ch, cv2.CV_32F, 0, 1))
        return mag * ch

    uism = 0.299 * _eme(edge(r)) + 0.587 * _eme(edge(g)) + 0.114 * _eme(edge(b))
    uiconm = _logamee(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32))
    return float(0.0282 * uicm + 0.2953 * uism + 3.5753 * uiconm)


def compute(image_bgr) -> dict:
    small = _prepare(image_bgr)
    return {"uiqm": round(uiqm(small), 3), "uciqe": round(uciqe(small), 3)}
