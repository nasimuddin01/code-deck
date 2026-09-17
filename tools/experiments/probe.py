"""Byte-toxicity probe. Five horizontal regions, streamed top to bottom:
  1 (rows 0-95):    solid RED           control
  2 (rows 96-191):  RED + pixels containing protocol command bytes (0x65,0xC5,...)
  3 (rows 192-287): solid GREEN         verdict strip for region 2
  4 (rows 288-383): RED + pixels containing control chars (0x0A,0x0D,0x11,0x13)
  5 (rows 384-479): solid BLUE          verdict strip for region 4
Corruption propagates downstream only. GREEN broken => firmware sniffs command
bytes. BLUE broken but GREEN clean => control-char translation. Both clean =>
neither theory.
"""
import sys, time
import numpy as np
sys.path.insert(0, ".")
from turzx.display import TurzxScreen, PORTRAIT, DISPLAY_BITMAP

W, H = 320, 480
buf = np.zeros((H, W), dtype="<u2")
RED, GREEN, BLUE = 0xF800, 0x07E0, 0x001F

buf[0:96, :] = RED
buf[96:192, :] = RED
# sprinkle command-byte pixels: LE bytes (0xC5,0x65) = DISPLAY_BITMAP,RESET ids
buf[96:192, ::8] = 0x65C5
buf[120:124, :] = 0x65C5          # a dense run too
buf[192:288, :] = GREEN
buf[288:384, :] = RED
buf[288:384, ::8] = 0x0A0A        # \n bytes
buf[300:304, :] = 0x1311          # XON/XOFF bytes
buf[320:324, :] = 0x0A0D          # \r\n bytes
buf[384:480, :] = BLUE

data = buf.tobytes()
assert len(data) == W * H * 2

scr = TurzxScreen(orientation=PORTRAIT)
scr.screen_on()
scr.set_brightness(80)
scr._cmd(DISPLAY_BITMAP, 0, 0, W - 1, H - 1)
chunk = W * 8
t0 = time.time()
for i in range(0, len(data), chunk):
    scr.ser.write(data[i:i + chunk])
    scr.ser.flush()
    time.sleep(0.002)
time.sleep(0.02)
print(f"probe sent in {time.time()-t0:.2f}s")
scr.close()
