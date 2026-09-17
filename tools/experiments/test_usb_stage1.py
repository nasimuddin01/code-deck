"""Stage 1: does the bulk path light the panel + show clean solids after init?"""
import time
from turzx.usbraw import UsbRaw

scr = UsbRaw()
print("claimed; sending vendor init", flush=True)
scr.init()
print("init done; cycling R/G/B solids", flush=True)
colors = [(220, 20, 20), (20, 200, 20), (20, 60, 230)]
names = ["RED", "GREEN", "BLUE"]
try:
    while True:
        for (c, n) in zip(colors, names):
            scr.solid(*c)
            print("solid", n, flush=True)
            time.sleep(4)
except KeyboardInterrupt:
    pass
finally:
    scr.close()
