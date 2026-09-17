"""Send the EXACT payload bytes that rendered clean on Windows."""
import sys, time
sys.path.insert(0, ".")
from turzx.display import TurzxScreen, PORTRAIT

data = open("diagnostics/turzx_startup-frame.rgb565le", "rb").read()
assert len(data) == 307200, len(data)

scr = TurzxScreen(orientation=PORTRAIT)
scr._cmd(0x6D)            # screen on
scr._cmd(0x6E, 51)        # brightness
time.sleep(0.05)
scr._cmd(0xC5, 0, 0, 319, 479)
time.sleep(0.0002)
t0 = time.time()
scr.ser.write(data)
scr.ser.flush()
print(f"windows-known-good payload sent in {time.time()-t0:.2f}s")
scr.close()
