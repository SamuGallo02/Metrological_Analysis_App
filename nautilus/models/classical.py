"""A fast, non-AI baseline. Also a minimal template for adding new models."""

from nautilus import Param, register
from nautilus.ops import apply_CLAHE, laplacian_sharpen, stretch_channels


@register(
    id="classical",
    name="Quick contrast boost",
    technical="Per-channel histogram stretch + CLAHE local contrast",
    description=(
        "Stretches each colour to remove the cast and boosts local contrast. Almost instant. "
        "Handy for browsing many photos quickly, or as a plain reference to compare the other "
        "methods against."
    ),
    params=[
        Param("white_balance", "Remove colour cast", True, type="bool",
              help="Stretches each colour channel to remove the blue/green tint."),
        Param("sharpen", "Sharpening", 0.0, min=0, max=0.5, step=0.01,
              help="Makes edges crisper. 0 turns it off."),
        Param("clip_limit", "Local contrast", 2.0, min=0, max=6, step=0.1,
              help="Brings out detail in dark and bright areas. 0 turns it off."),
    ],
    order=90,
)
def classical(image, white_balance, sharpen, clip_limit):
    if white_balance:
        image = stretch_channels(image)
    if sharpen > 0:
        image = laplacian_sharpen(image, alpha=sharpen)
    if clip_limit > 0:
        image = apply_CLAHE(image, clip_limit=clip_limit)
    return image
