"""RGB565-LE conversion with a command-byte filter for the TURZX panel.

The panel executes protocol command codes if they appear where it expects a
command. Under any residual stream desync, a stray command byte inside pixel
data can blank or reset the screen. We remap every pixel whose RGB565-LE bytes
contain a command code to the nearest visually-identical safe colour. The LUT is
built once and cached to disk (~2 s to build, instant to load).
"""
from __future__ import annotations
import os
import numpy as np
from PIL import Image

# Protocol command codes that must never appear as a pixel byte.
FORBIDDEN = frozenset([40, 41, 69, 255] + list(range(101, 111)) + [121, 122, 130, 131]
                      + list(range(160, 181)) + list(range(194, 213)))

_CACHE = os.path.join(os.path.dirname(__file__), "_rgb565_safe_lut.npy")
_LUT: np.ndarray | None = None


def _build_lut() -> np.ndarray:
    lut = np.arange(65536, dtype=np.uint16)
    for v in range(65536):
        if (v & 0xFF) not in FORBIDDEN and (v >> 8) not in FORBIDDEN:
            continue
        r, g, b = v >> 11, (v >> 5) & 0x3F, v & 0x1F
        best, bc = v, 1 << 30
        for dr in (0, -1, 1, -2, 2):
            nr = r + dr
            if not 0 <= nr <= 31:
                continue
            for dg in (0, -1, 1, -2, 2):
                ng = g + dg
                if not 0 <= ng <= 63:
                    continue
                for db in (0, -1, 1, -2, 2):
                    nb = b + db
                    if not 0 <= nb <= 31:
                        continue
                    nv = (nr << 11) | (ng << 5) | nb
                    if (nv & 0xFF) in FORBIDDEN or (nv >> 8) in FORBIDDEN:
                        continue
                    cost = (dr * 2) ** 2 + dg ** 2 + (db * 2) ** 2
                    if cost < bc:
                        best, bc = nv, cost
        lut[v] = best
    return lut


def lut() -> np.ndarray:
    global _LUT
    if _LUT is None:
        if os.path.exists(_CACHE):
            _LUT = np.load(_CACHE)
        else:
            _LUT = _build_lut()
            try:
                np.save(_CACHE, _LUT)
            except OSError:
                pass
    return _LUT


def to_rgb565le(image: Image.Image) -> bytes:
    a = np.asarray(image.convert("RGB"), dtype=np.uint16)
    r, g, b = a[..., 0] >> 3, a[..., 1] >> 2, a[..., 2] >> 3
    px = ((r << 11) | (g << 5) | b).astype(np.uint16)
    return lut()[px].astype("<u2").tobytes()
