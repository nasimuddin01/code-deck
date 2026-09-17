"""Vendor-faithful send: cmd, 10ms pause, then ONE uninterrupted write.
Frame A = command 197, frame B = command 198. Giant corner badge identifies each.
"""
import sys, time
sys.path.insert(0, ".")
from PIL import ImageDraw, ImageFont
from turzx.display import TurzxScreen, PORTRAIT, DISPLAY_BITMAP
from dashboard.render import render
from dashboard.stats import DummyStatsProvider

def badge(img, letter):
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", 90)
    d.rectangle([230, 390, 315, 475], fill="#ffffff")
    d.text((272, 432), letter, font=f, anchor="mm", fill="#000000")
    return img

def send(scr, img, cmd):
    data = TurzxScreen._to_rgb565le(img)
    scr._cmd(cmd, 0, 0, 319, 479)
    time.sleep(0.010)               # vendor: pause between command and payload
    t0 = time.time()
    scr.ser.write(data)             # vendor: single write, no chunking, no flush
    scr.ser.flush()
    print(f"cmd {cmd}: payload written in {time.time()-t0:.2f}s")
    time.sleep(0.02)

scr = TurzxScreen(orientation=PORTRAIT)
scr.screen_on()
scr.set_brightness(80)
stats = DummyStatsProvider().get_stats()

print("frame A (cmd 197)...")
send(scr, badge(render(stats), "A"), 197)
time.sleep(20)
print("frame B (cmd 198)...")
send(scr, badge(render(stats), "B"), 198)
scr.close()
print("done - which frames were clean?")
