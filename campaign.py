"""Autonomous transport-strategy campaign for the TURZX screen.

Cycles strategies forever. Each frame carries a giant ID number.
Strategy 0 = solid bands control (must always be clean).
User reports which number looks clean; that strategy wins.
"""
import sys, time, traceback
sys.path.insert(0, ".")
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from turzx.display import TurzxScreen, PORTRAIT
from dashboard.render import render
from dashboard.stats import DummyStatsProvider

W, H = 320, 480
ROW = W * 2

def labeled_dashboard(n, caption):
    img = render(DummyStatsProvider().get_stats())
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", 110)
    f2 = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", 16)
    d.rounded_rectangle([8, 350, 150, 472], radius=10, fill="#ffffff")
    d.text((79, 408), str(n), font=f, anchor="mm", fill="#000000")
    d.text((160, 460), caption, font=f2, fill="#ffffff")
    return TurzxScreen._to_rgb565le(img)

def bands_payload():
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, H // 3], fill=(255, 0, 0))
    d.rectangle([0, H // 3, W, 2 * H // 3], fill=(0, 255, 0))
    d.rectangle([0, 2 * H // 3, W, H], fill=(0, 0, 255))
    rgb = np.asarray(img, dtype=np.uint16)
    px = ((rgb[..., 0] >> 3) << 11) | ((rgb[..., 1] >> 2) << 5) | (rgb[..., 2] >> 3)
    return px.astype("<u2").tobytes()

def send_window(scr, cmd, y0, y1, data, presleep=0.001):
    scr._cmd(cmd, 0, y0, W - 1, y1)
    time.sleep(presleep)
    scr.ser.write(data)
    scr.ser.flush()

def full(scr, payload, cmd=0xC5, chunk=None, gap=0.0):
    scr._cmd(cmd, 0, 0, W - 1, H - 1)
    time.sleep(0.001)
    if chunk is None:
        scr.ser.write(payload); scr.ser.flush()
    else:
        for i in range(0, len(payload), chunk):
            scr.ser.write(payload[i:i + chunk]); scr.ser.flush()
            if gap: time.sleep(gap)

def strips(scr, payload, rows, cmd, gap):
    for y0 in range(0, H, rows):
        y1 = min(y0 + rows, H) - 1
        send_window(scr, cmd, y0, y1, payload[y0 * ROW:(y1 + 1) * ROW])
        time.sleep(gap)

def linecoding_dance(scr):
    s = scr.ser
    s.dtr = False; s.rts = False; time.sleep(0.02)
    s.rts = True; time.sleep(0.02)
    s.dtr = True; time.sleep(0.02)
    for rate in (115200, 100663296, 115200, 100663296):
        try: s.baudrate = rate
        except Exception as e: print(f"    baud {rate} failed: {e}")
        time.sleep(0.02)

STRATEGIES = [
    ("0 CONTROL bands full-frame",        lambda s, p: full(s, bands_payload())),
    ("1 strips 12row via C5 5ms",         lambda s, p: strips(s, p, 12, 0xC5, 0.005)),
    ("2 strips 12row via C6 5ms",         lambda s, p: strips(s, p, 12, 0xC6, 0.005)),
    ("3 strips 48row via C6 10ms",        lambda s, p: strips(s, p, 48, 0xC6, 0.010)),
    ("4 slow full 640B/15ms (~7s)",       lambda s, p: full(s, p, chunk=640, gap=0.015)),
    ("5 vslow full 640B/40ms (~19s)",     lambda s, p: full(s, p, chunk=640, gap=0.040)),
    ("6 row-aligned 3840B/30ms",          lambda s, p: full(s, p, chunk=3840, gap=0.030)),
    ("7 linecoding dance + full",         lambda s, p: (linecoding_dance(s), full(s, p))),
    ("8 CLEAR then full",                 lambda s, p: (s._cmd(0x66), time.sleep(0.3), full(s, p))),
    ("9 strips 4row via C5 3ms",          lambda s, p: strips(s, p, 4, 0xC5, 0.003)),
    ("10 crawl full 320B/60ms (~60s)",    lambda s, p: full(s, p, chunk=320, gap=0.060)),
]

def main():
    scr = None
    cycle = 0
    while True:
        cycle += 1
        for idx, (name, fn) in enumerate(STRATEGIES):
            try:
                if scr is None:
                    scr = TurzxScreen(orientation=PORTRAIT)
                    scr._cmd(0x6D); scr._cmd(0x6E, 51); time.sleep(0.05)
                payload = bands_payload() if idx == 0 else labeled_dashboard(idx, name)
                t0 = time.time()
                fn(scr, payload)
                print(f"cycle {cycle} strategy [{name}] sent in {time.time()-t0:.1f}s", flush=True)
                time.sleep(18)
            except KeyboardInterrupt:
                return
            except Exception as e:
                print(f"strategy [{name}] error: {e}", flush=True)
                traceback.print_exc()
                try:
                    if scr: scr.close()
                except Exception: pass
                scr = None
                time.sleep(3)

main()
