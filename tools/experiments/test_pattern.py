"""Proof of life: portrait test pattern, native panel mode (no orientation cmd)."""
import sys
sys.path.insert(0, ".")
from PIL import Image, ImageDraw, ImageFont
from turzx.display import TurzxScreen, PORTRAIT

scr = TurzxScreen(orientation=PORTRAIT)
print(f"connected on {scr.ser.port}, {scr.width}x{scr.height} portrait")
scr.screen_on()
scr.set_brightness(80)

W, H = scr.width, scr.height  # 320x480
img = Image.new("RGB", (W, H), "black")
d = ImageDraw.Draw(img)

bars = [(255,0,0),(0,255,0),(0,0,255),(255,255,0),(0,255,255),(255,0,255),(255,255,255)]
bh = (H // 2 - 40) // len(bars)
for i, c in enumerate(bars):
    d.rectangle([0, i*bh, W - 1, (i+1)*bh - 1], fill=c)

for x in range(W):
    v = int(255 * x / W)
    d.line([(x, H//2 - 30), (x, H//2 + 10)], fill=(v, v, v))

for cx, cy in [(0,0),(W-1,0),(0,H-1),(W-1,H-1)]:
    d.rectangle([max(0,cx-14), max(0,cy-14), min(W-1,cx+14), min(H-1,cy+14)], outline=(255,128,0), width=4)

font = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", 26)
d.text((W//2, H//2 + 70), "TURZX ALIVE", font=font, anchor="mm", fill=(0, 255, 128))
d.text((W//2, H//2 + 110), f"{W}x{H} portrait", font=font, anchor="mm", fill=(200, 200, 200))
d.text((W//2, H//2 + 150), "RED bar on TOP?", font=font, anchor="mm", fill=(255, 200, 0))

scr.draw(img)
img.save("test_pattern_sent.png")
print("portrait pattern sent")
scr.close()
