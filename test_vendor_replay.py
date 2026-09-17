"""Replay the vendor's exact wire behavior from the Windows capture.

Frame A: vendor init sequence (FF, brightness 0, screen-on, mirror,
         orientation, brightness) at 115200, then full-frame C5 + single write.
Frame B: same, after switching line coding to the magic 0x06000000
         (100,663,296) observed as the final state on Windows.
"""
import glob, sys, time
sys.path.insert(0, ".")
from PIL import ImageDraw, ImageFont
from turzx.display import TurzxScreen, PORTRAIT
from dashboard.render import render
from dashboard.stats import DummyStatsProvider

if not glob.glob("/dev/cu.usbmodemUSB35INCH*"):
    sys.exit("SCREEN NOT CONNECTED to the Mac - plug it back in and rerun")

def badge(img, letter):
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", 90)
    d.rectangle([230, 390, 315, 475], fill="#ffffff")
    d.text((272, 432), letter, font=f, anchor="mm", fill="#000000")
    return img

def vendor_init(scr):
    scr._cmd(0xFF)                                   # vendor: first command
    scr._cmd(0x6E, 0)                                # brightness raw 0 (max)
    scr._cmd(0x6D)                                   # screen on
    buf = bytearray(16); buf[5] = 0x7A               # mirror off, 16-byte
    scr.ser.write(bytes(buf))
    scr.ser.write(bytes.fromhex("00000000007964014001e0000000000000")[:16])  # portrait 320x480
    scr._cmd(0x6E, 51)                               # brightness ~80%
    time.sleep(0.05)

def send_frame(scr, img):
    data = TurzxScreen._to_rgb565le(img)
    scr._cmd(0xC5, 0, 0, 319, 479)
    time.sleep(0.0002)                               # vendor: ~200 microseconds
    t0 = time.time()
    scr.ser.write(data)
    scr.ser.flush()
    return time.time() - t0

scr = TurzxScreen(orientation=PORTRAIT)
stats = DummyStatsProvider().get_stats()

print("frame A: vendor init @115200 ...")
vendor_init(scr)
dt = send_frame(scr, badge(render(stats), "A"))
print(f"  payload drained in {dt:.2f}s")

time.sleep(15)

print("switching line coding to 100663296 ...")
try:
    scr.ser.baudrate = 100663296
    print("  line coding set OK")
except Exception as e:
    print(f"  FAILED: {e}")
    scr.close()
    sys.exit(1)
time.sleep(0.3)

print("frame B: vendor init @magic rate ...")
vendor_init(scr)
dt = send_frame(scr, badge(render(stats), "B"))
print(f"  payload drained in {dt:.2f}s")
scr.close()
print("done - report frame A vs frame B")
