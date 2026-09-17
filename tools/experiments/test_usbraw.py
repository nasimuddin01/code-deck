"""Draw the test card via raw USB bulk. Run: sudo .venv/bin/python test_usbraw.py"""
import time
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from turzx.usbraw import UsbRaw

W, H = 320, 480

def font(sz):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", sz)
    except Exception:
        return ImageFont.load_default()

def card(label):
    img = Image.new("RGB", (W, H), (12, 12, 16))
    d = ImageDraw.Draw(img)
    for y in range(H):
        c = int(255 * y / (H - 1))
        d.line([(W - 40, y), (W - 1, y)], fill=(c, 255 - c, (c * 2) % 256))
    f = font(16)
    for y in range(0, H, 40):
        d.line([(0, y), (W - 44, y)], fill=(70, 70, 80))
        d.text((4, y + 2), f"y={y}", font=f, fill=(200, 200, 210))
    d.line([(0, 0), (W - 1, H - 1)], fill=(0, 240, 255), width=2)
    d.line([(0, H - 1), (W - 1, 0)], fill=(255, 120, 0), width=2)
    d.rectangle([40, 200, 280, 280], fill=(0, 0, 0))
    d.text((60, 214), label, font=font(46), fill=(255, 255, 255))
    return img

def to565(img):
    a = np.asarray(img.convert("RGB"), dtype=np.uint16)
    r, g, b = a[..., 0] >> 3, a[..., 1] >> 2, a[..., 2] >> 3
    return ((r << 11) | (g << 5) | b).astype("<u2").tobytes()

if __name__ == "__main__":
    scr = UsbRaw()
    print("claimed device via libusb; drawing USB-BULK card", flush=True)
    try:
        while True:
            scr.draw_full(to565(card("USB")), W, H)
            print("frame sent", flush=True)
            time.sleep(8)
    except KeyboardInterrupt:
        pass
    finally:
        scr.close()
