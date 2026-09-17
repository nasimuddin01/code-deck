"""Dirty-rectangle detection between two frames (pure numpy)."""
from __future__ import annotations

import numpy as np
from PIL import Image

BBox = tuple[int, int, int, int]  # x0, y0, x1, y1 (exclusive)


def bbox(a: Image.Image | np.ndarray, b: Image.Image | np.ndarray) -> BBox | None:
    """Smallest rectangle covering every differing pixel, or None if equal."""
    aa = np.asarray(a.convert("RGB") if isinstance(a, Image.Image) else a)
    bb = np.asarray(b.convert("RGB") if isinstance(b, Image.Image) else b)
    if aa.shape != bb.shape:
        h, w = bb.shape[:2]
        return (0, 0, w, h)
    diff = np.any(aa != bb, axis=2)
    rows = np.flatnonzero(diff.any(axis=1))
    if rows.size == 0:
        return None
    cols = np.flatnonzero(diff.any(axis=0))
    return (int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1)


def area(box: BBox) -> int:
    return (box[2] - box[0]) * (box[3] - box[1])
