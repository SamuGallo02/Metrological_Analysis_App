"""Contact sheet: the original next to each method's result, labelled, in one image."""

import math

import cv2
import numpy as np

BACKGROUND = (32, 32, 32)
GAP = 8
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _labelled(title, detail, image, width, height):
    """One cell: a label bar with ``title`` (white) and ``detail`` (grey) over the resized image."""
    bar = max(28, width // 18)
    cell = np.full((bar + height, width, 3), BACKGROUND, np.uint8)
    cell[bar:] = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    scale, thick = bar / 50, max(1, round(bar / 20))
    space = bar // 2
    title_w = cv2.getTextSize(title, FONT, scale, thick)[0][0]
    detail_w = cv2.getTextSize(detail, FONT, scale * 0.75, thick)[0][0] if detail else -space
    fit = min(1.0, (width - 2 * (bar // 3)) / (title_w + space + detail_w))  # shrink long labels
    scale, title_w, space = scale * fit, title_w * fit, space * fit
    y = round(bar * 0.68)
    cv2.putText(cell, title, (bar // 3, y), FONT, scale, (255, 255, 255), thick, cv2.LINE_AA)
    if detail:
        cv2.putText(cell, detail, (round(bar // 3 + title_w + space), y), FONT, scale * 0.75,
                    (170, 170, 170), max(1, thick - 1), cv2.LINE_AA)
    return cell


def make_sheet(tiles, width=1000):
    """Arrange ``tiles``, a list of (title, detail, image) of the same size, in a labelled grid.

    Each image is scaled to ``width`` pixels; the grid is about as wide as it is tall.
    Only ASCII text can be drawn.
    """
    h, w = tiles[0][2].shape[:2]
    height = round(h * width / w)
    cells = [_labelled(title, detail, image, width, height) for title, detail, image in tiles]
    cols = math.ceil(math.sqrt(len(cells)))
    rows = math.ceil(len(cells) / cols)
    ch, cw = cells[0].shape[:2]
    sheet = np.full((rows * ch + (rows + 1) * GAP, cols * cw + (cols + 1) * GAP, 3), BACKGROUND, np.uint8)
    for i, cell in enumerate(cells):
        r, c = divmod(i, cols)
        y, x = GAP + r * (ch + GAP), GAP + c * (cw + GAP)
        sheet[y:y + ch, x:x + cw] = cell
    return sheet
