"""The v1 PIL render loop — `code-deck serve --renderer pil`.

Kept as the safety net until the Chromium pipeline replaces it. This is the
original run_dashboard.py loop with logging, configurable paths and the overlay
decision moved into AttentionTracker. Frame rate is bounded by the ~1.9 s
full-frame USB push.
"""
from __future__ import annotations

import logging
import time

from ..config import PREVIEW_PATH, ensure_dirs
from ..providers.live import LiveStatsProvider
from ..providers.stats import DummyStatsProvider
from ..state.attention import AttentionTracker, Overlay
from .pil_legacy import overlay_needs_you, render

log = logging.getLogger(__name__)


class LegacyLoop:
    def __init__(self, *, interval: float, brightness: int, overlay_enabled: bool,
                 overlay_seconds: float, no_device: bool = False) -> None:
        self.interval = interval
        self.brightness = brightness
        self.no_device = no_device
        self.tracker = AttentionTracker(enabled=overlay_enabled, seconds=overlay_seconds)
        self.live = LiveStatsProvider()
        self.fallback = DummyStatsProvider()

    def _stats(self):
        try:
            return self.live.get_stats()
        except Exception as e:  # never let a parse hiccup blank the screen
            log.warning("live stats failed (%s); using dummy", e)
            return self.fallback.get_stats()

    def _push(self, scr, img) -> None:
        if scr is not None:
            scr.draw(img)
        try:
            img.save(PREVIEW_PATH)
        except OSError:
            pass

    def _play_overlay(self, scr, base, ov: Overlay) -> None:
        """Push a fading banner over `base` for ~ov.seconds, then restore it."""
        if scr is not None:
            scr.set_brightness(self.brightness)
        while True:
            elapsed = time.time() - ov.started_at
            if elapsed >= ov.seconds:
                break
            self._push(scr, overlay_needs_you(base, ov.label, 1.0 - elapsed / ov.seconds, ov.kind))
            if scr is None:
                time.sleep(0.5)
        self._push(scr, base)

    def run(self) -> None:
        ensure_dirs()
        scr = None
        while True:
            try:
                if scr is None and not self.no_device:
                    from ..turzx.usbraw import UsbRaw  # lazy: needs libusb
                    scr = UsbRaw()
                    scr.init(brightness_param=self.brightness)
                    log.info("connected via libusb: %dx%d", scr.width, scr.height)
                stats = self._stats()
                frame = render(stats)
                if scr is not None:
                    scr.set_brightness(self.brightness)  # insurance against a stray dark frame
                t0 = time.time()
                self._push(scr, frame)
                log.debug("frame pushed in %.2fs", time.time() - t0)

                started = self.tracker.update(stats, time.time())
                if started:
                    ov = started[0]
                    log.info("overlay [%s]: %s", ov.kind, ov.label)
                    self._play_overlay(scr, frame, ov)
                else:
                    time.sleep(self.interval)
            except KeyboardInterrupt:
                break
            except Exception as e:  # screen unplugged, USB hiccup, libusb missing...
                log.warning("%s; retrying in 3s", e)
                try:
                    if scr is not None:
                        scr.close()
                except Exception:
                    pass
                scr = None
                time.sleep(3)
        if scr is not None:
            scr.close()
