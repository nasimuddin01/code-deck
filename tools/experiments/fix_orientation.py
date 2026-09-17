"""Force the panel back to portrait addressing, then draw the dashboard once."""
import sys, time
sys.path.insert(0, ".")
from turzx.display import TurzxScreen, PORTRAIT
from dashboard.render import render
from dashboard.stats import DummyStatsProvider

print("connect #1, commanding PORTRAIT...")
scr = TurzxScreen(orientation=PORTRAIT)
scr.set_orientation(PORTRAIT)   # explicit: width=320 height=480 in packet
time.sleep(0.5)
print("hardware reset to apply saved state...")
scr.reset()

time.sleep(3)
deadline = time.time() + 25
while True:
    try:
        scr = TurzxScreen(orientation=PORTRAIT)
        break
    except Exception:
        if time.time() > deadline:
            sys.exit("no re-enumeration")
        time.sleep(1)
print("connect #2, commanding PORTRAIT again...")
scr.set_orientation(PORTRAIT)
time.sleep(0.5)
scr.screen_on()
scr.set_brightness(80)

frame = render(DummyStatsProvider().get_stats())
t0 = time.time()
scr.draw(frame)
print(f"dashboard frame sent in {time.time()-t0:.2f}s -- check the screen")
scr.close()
