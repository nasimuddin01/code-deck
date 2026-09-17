"""Stage 3: bulk draw with command-byte-filtered payload + per-frame brightness.

Strips the panel's protocol command codes out of the pixel data so that even if
the stream desyncs, no stray byte can fire screen-off/brightness/reset. Lets us
see the TRUE corruption state (clean vs stripe) without the screen blanking.
"""
import time
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from turzx.usbraw import UsbRaw

W, H = 320, 480
FORBIDDEN = frozenset([40,41,69,255] + list(range(101,111)) + [121,122,130,131]
                      + list(range(160,181)) + list(range(194,213)))

def build_lut():
    lut = np.arange(65536, dtype=np.uint16)
    for v in range(65536):
        if (v & 0xFF) not in FORBIDDEN and (v >> 8) not in FORBIDDEN:
            continue
        r,g,b = v>>11, (v>>5)&0x3F, v&0x1F
        best,bc = v, 1<<30
        for dr in (0,-1,1,-2,2):
            nr=r+dr
            if not 0<=nr<=31: continue
            for dg in (0,-1,1,-2,2):
                ng=g+dg
                if not 0<=ng<=63: continue
                for db in (0,-1,1,-2,2):
                    nb=b+db
                    if not 0<=nb<=31: continue
                    nv=(nr<<11)|(ng<<5)|nb
                    if (nv&0xFF) in FORBIDDEN or (nv>>8) in FORBIDDEN: continue
                    cost=(dr*2)**2+dg**2+(db*2)**2
                    if cost<bc: best,bc=nv,cost
        lut[v]=best
    return lut

def font(sz):
    try: return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", sz)
    except Exception: return ImageFont.load_default()

def card():
    img = Image.new("RGB", (W, H), (12, 12, 16)); d = ImageDraw.Draw(img)
    for y in range(H):
        c = int(255 * y / (H - 1)); d.line([(W-40, y), (W-1, y)], fill=(c, 255-c, (c*2)%256))
    f = font(16)
    for y in range(0, H, 40):
        d.line([(0, y), (W-44, y)], fill=(70,70,80)); d.text((4, y+2), f"y={y}", font=f, fill=(200,200,210))
    d.line([(0,0),(W-1,H-1)], fill=(0,240,255), width=3)
    d.line([(0,H-1),(W-1,0)], fill=(255,120,0), width=3)
    d.rectangle([40,200,280,280], fill=(30,30,30)); d.text((70,214), "USB3", font=font(40), fill=(255,255,255))
    return img

print("building command-byte filter LUT ...", flush=True)
LUT = build_lut()
def to565(img):
    a = np.asarray(img.convert("RGB"), dtype=np.uint16)
    r,g,b = a[...,0]>>3, a[...,1]>>2, a[...,2]>>3
    px = ((r<<11)|(g<<5)|b).astype(np.uint16)
    return LUT[px].astype("<u2").tobytes()

scr = UsbRaw(); print("claimed; init", flush=True); scr.init()
data = to565(card()); print("drawing FILTERED card via bulk", flush=True)
try:
    while True:
        scr.cmd(0x6E, x0=39)          # re-assert brightness each frame
        time.sleep(0.005)
        scr.draw_full(data, W, H)
        print("filtered card frame", flush=True); time.sleep(6)
except KeyboardInterrupt: pass
finally: scr.close()
