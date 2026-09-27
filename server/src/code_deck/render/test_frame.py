"""The 'can you see this?' frame the setup wizard (CLI and GUI) shows."""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

W, H = 320, 480


def test_frame() -> Image.Image:
    img = Image.new("RGB", (W, H), (26, 26, 25))
    d = ImageDraw.Draw(img)
    try:
        big, small = ImageFont.load_default(size=34), ImageFont.load_default(size=16)
    except TypeError:                       # Pillow < 10.1
        big = small = ImageFont.load_default()
    d.text((24, 60), "CODE DECK", fill=(236, 236, 232), font=big)
    d.text((24, 108), "setup check", fill=(150, 150, 145), font=small)
    for i, c in enumerate([(217, 89, 38), (154, 111, 240), (57, 135, 229)]):
        d.rounded_rectangle((24, 170 + i * 70, 296, 220 + i * 70), radius=12, fill=c)
    d.text((24, 400), "if you can read this,", fill=(150, 150, 145), font=small)
    d.text((24, 424), "the USB connection works", fill=(74, 163, 255), font=small)
    return img
