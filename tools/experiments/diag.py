"""Diagnostic: hardware reset, HELLO probe, then 3 solid color bands.

Expected on a healthy 320x480 portrait RGB565LE panel:
  clean RED band on top, GREEN in middle, BLUE at bottom.
Byte-swapped panel would show roughly: teal-blue / dark red / green.
Stride mismatch would show vertical striping (solid bands are immune to
stride, so striping here would mean data loss instead).
"""
import glob
import sys
import time

sys.path.insert(0, ".")
from PIL import Image, ImageDraw
from turzx.display import PORTRAIT, TurzxScreen

print("opening + RESET...")
scr = TurzxScreen(orientation=PORTRAIT)
scr.reset()
print("reset sent; waiting for re-enumeration...")
deadline = time.time() + 25
port = None
time.sleep(3)
while time.time() < deadline:
    m = glob.glob("/dev/cu.usbmodemUSB35INCH*")
    if m:
        port = m[0]
        break
    time.sleep(1)
if not port:
    sys.exit("device did not come back after reset")
print(f"back on {port}")
time.sleep(2)

scr = TurzxScreen(port=port, orientation=PORTRAIT)
resp = scr.hello()
print(f"HELLO response: {resp.hex() if resp else '(silent - classic Turing 3.5 rev A)'}")

scr.screen_on()
scr.set_brightness(80)

W, H = 320, 480
img = Image.new("RGB", (W, H))
d = ImageDraw.Draw(img)
d.rectangle([0, 0, W, H // 3], fill=(255, 0, 0))
d.rectangle([0, H // 3, W, 2 * H // 3], fill=(0, 255, 0))
d.rectangle([0, 2 * H // 3, W, H], fill=(0, 0, 255))

t0 = time.time()
scr.draw(img)
print(f"bands frame sent in {time.time() - t0:.2f}s (expect RED / GREEN / BLUE top-to-bottom)")
scr.close()
