import numpy as np
from PIL import Image

from code_deck.turzx import pixels


def test_no_forbidden_bytes_in_output(tmp_path, monkeypatch):
    monkeypatch.setattr(pixels, "_CACHE", str(tmp_path / "lut.npy"))
    monkeypatch.setattr(pixels, "_LUT", None)
    # a gradient covering many colours, including ones whose RGB565 bytes
    # would be protocol command codes
    a = np.zeros((64, 256, 3), dtype=np.uint8)
    a[..., 0] = np.arange(256)[None, :]
    a[..., 1] = np.arange(64)[:, None] * 4
    a[..., 2] = 255 - np.arange(256)[None, :]
    data = pixels.to_rgb565le(Image.fromarray(a))
    assert len(data) == 64 * 256 * 2
    assert not (set(data) & pixels.FORBIDDEN)
    assert (tmp_path / "lut.npy").exists()  # cache written under the given dir


def test_lut_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(pixels, "_CACHE", str(tmp_path / "lut.npy"))
    monkeypatch.setattr(pixels, "_LUT", None)
    first = pixels.lut().copy()
    monkeypatch.setattr(pixels, "_LUT", None)
    assert np.array_equal(pixels.lut(), first)
