import sys, time
sys.path.insert(0, ".")
import numpy as np
from PIL import ImageDraw, ImageFont
from turzx.display import TurzxScreen, PORTRAIT
from dashboard.render import render
from dashboard.stats import DummyStatsProvider

img = render(DummyStatsProvider().get_stats())
d = ImageDraw.Draw(img)
f = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", 90)
d.rectangle([230, 390, 315, 475], fill="#ffffff")
d.text((272, 432), "D", font=f, anchor="mm", fill="#000000")

data = TurzxScreen._to_rgb565le(img)
w = np.frombuffer(data, dtype="<u2")
changes = np.flatnonzero(np.diff(w) != 0)
runs = np.diff(np.concatenate([[-1], changes, [len(w) - 1]]))
print(f"longest identical-pixel run after dither: {runs.max()} px")

time.sleep(45)  # let the user inspect the fixture frame first
scr = TurzxScreen(orientation=PORTRAIT)
scr._cmd(0x6D); scr._cmd(0x6E, 51); time.sleep(0.05)
scr._cmd(0xC5, 0, 0, 319, 479); time.sleep(0.0002)
scr.ser.write(data); scr.ser.flush()
print("dithered dashboard (badge D) sent")
scr.close()
