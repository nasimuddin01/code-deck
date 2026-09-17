"""code-display: TURZX dashboard runner (raw-USB transport)."""
import sys
import time

sys.path.insert(0, ".")
from dashboard.render import render, overlay_needs_you
from dashboard.live import LiveStatsProvider
from dashboard.stats import DummyStatsProvider
from turzx.usbraw import UsbRaw

INTERVAL = 10           # seconds between refreshes
OVERLAY_ENABLED = True  # show a full-screen banner when a session first needs you
OVERLAY_SECONDS = 10    # how long that banner stays before it finishes fading out


def _needs_you(stats) -> dict[str, tuple[str, str]]:
    """{session_id: (label, kind)} for sessions currently awaiting the user.

    kind is "idle" (turn ended) or "needs" (blocked on you)."""
    out: dict[str, tuple[str, str]] = {}
    for st in stats:
        for s in st.sessions:
            if s.needs_input:
                out[s.id] = (s.label, s.attention_kind or "needs")
    return out


def _play_overlay(scr, base, label: str, kind: str) -> None:
    """Push a fading attention banner over `base` for ~OVERLAY_SECONDS, then
    restore the clean frame. Frame rate is bounded by the ~1.9s USB push."""
    scr.set_brightness(39)
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed >= OVERLAY_SECONDS:
            break
        img = overlay_needs_you(base, label, 1.0 - elapsed / OVERLAY_SECONDS, kind)
        scr.draw(img)
        img.save("preview.png")
    scr.draw(base)          # clear the overlay
    base.save("preview.png")


def main() -> None:
    live = LiveStatsProvider()
    fallback = DummyStatsProvider()

    def get_stats():
        try:
            return live.get_stats()
        except Exception as e:  # never let a parse hiccup blank the screen
            print(f"live stats failed ({e}); using dummy", flush=True)
            return fallback.get_stats()

    scr = None
    announced: set[tuple[str, str]] = set()  # (session_id, kind) already shown
    while True:
        try:
            if scr is None:
                scr = UsbRaw()
                scr.init(brightness_param=39)
                print(f"connected via libusb: {scr.width}x{scr.height}", flush=True)
            stats = get_stats()
            frame = render(stats)
            scr.set_brightness(39)          # insurance against a stray dark frame
            t0 = time.time()
            scr.draw(frame)
            frame.save("preview.png")
            print(f"frame pushed in {time.time() - t0:.2f}s", flush=True)

            needs = _needs_you(stats)
            # key on (id, kind) so a session that changes state (idle -> needs)
            # re-announces with the right banner
            keys = {(sid, kind) for sid, (_, kind) in needs.items()}
            new = [k for k in keys if k not in announced]
            announced = keys                # drop cleared sessions, keep current
            # overlay only for a real "needs you"; idle ("turn ended") shows as
            # the row status in the list, no full-screen banner
            overlay_new = [k for k in new if k[1] != "idle"]
            if OVERLAY_ENABLED and overlay_new:
                sid, kind = overlay_new[0]
                label = needs[sid][0]
                print(f"needs-you overlay [{kind}]: {label}", flush=True)
                _play_overlay(scr, frame, label, kind)
            else:
                time.sleep(INTERVAL)
        except KeyboardInterrupt:
            break
        except Exception as e:  # screen unplugged, USB hiccup...
            print(f"error: {e}; reconnecting in 3s", flush=True)
            try:
                if scr:
                    scr.close()
            except Exception:
                pass
            scr = None
            time.sleep(3)


if __name__ == "__main__":
    main()
