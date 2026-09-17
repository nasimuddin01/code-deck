"""Content bisect round 1: 8 slices of the real dashboard payload,
each followed by a 12-row solid GREEN verdict strip.
GREEN strip = phase intact so far. MAGENTA/PINK strip = odd byte slip upstream.
"""
import sys, time
sys.path.insert(0, ".")
from PIL import Image
from turzx.display import TurzxScreen, PORTRAIT
from dashboard.render import render
from dashboard.stats import DummyStatsProvider

dash = render(DummyStatsProvider().get_stats())
out = Image.new("RGB", (320, 480), "black")
GREEN = (0, 255, 0)
for k in range(8):
    slice_ = dash.crop((0, k * 48, 320, (k + 1) * 48))
    out.paste(slice_, (0, k * 60))
    strip = Image.new("RGB", (320, 12), GREEN)
    out.paste(strip, (0, k * 60 + 48))

out.save("bisect1_sent.png")
scr = TurzxScreen(orientation=PORTRAIT)
scr.screen_on()
scr.set_brightness(80)
scr.draw(out)
print("bisect frame 1 sent")
scr.close()
