"""The v1 PIL renderer as a device-loop thread — `code-deck serve --renderer pil`.

Reads everything from the StateStore (the samplers own the providers and the
overlay decision); this thread owns the USB device. Kept as the safety net until
the Chromium pipeline replaces it. Frame rate is bounded by the ~1.9 s
full-frame USB push.
"""
from __future__ import annotations

import logging
import threading
import time

from ..config import PREVIEW_PATH, ensure_dirs
from ..state.store import StateStore
from .pil_legacy import overlay_needs_you, render

log = logging.getLogger(__name__)


class PilDeviceLoop(threading.Thread):
    def __init__(self, store: StateStore, stop: threading.Event, *,
                 interval: float, no_device: bool = False) -> None:
        super().__init__(name="device-loop", daemon=True)
        self.store = store
        self.stop_event = stop
        self.interval = interval
        self.no_device = no_device
        self._brightness_applied: int | None = None
        self._last_overlay_start: float | None = None

    # -- device helpers -----------------------------------------------------
    def _brightness(self) -> int:
        b = self.store.get("device").get("brightness")
        return 39 if b is None else int(b)

    def _push(self, scr, img) -> None:
        t0 = time.time()
        if scr is not None:
            scr.draw(img)
        try:
            img.save(PREVIEW_PATH)
        except OSError:
            pass
        self.store.update_device(
            last_push_ms=int((time.time() - t0) * 1000),
            last_rect=[0, 0, img.width, img.height],
            frames_pushed=self.store.get("device")["frames_pushed"] + 1)

    def _play_overlay(self, scr, base, ov: dict) -> None:
        """Push a fading banner over `base` until ov expires, then restore it."""
        while not self.stop_event.is_set():
            elapsed = time.time() - ov["started_at"]
            if elapsed >= ov["seconds"]:
                break
            self._push(scr, overlay_needs_you(base, ov["label"],
                                              1.0 - elapsed / ov["seconds"], ov["kind"]))
            if scr is None:
                time.sleep(0.5)
        self._push(scr, base)

    # -- main loop ----------------------------------------------------------
    def run(self) -> None:
        ensure_dirs()
        self.store.update_device(renderer="pil")
        scr = None
        while not self.stop_event.is_set():
            try:
                if scr is None and not self.no_device:
                    from ..turzx.usbraw import UsbRaw  # lazy: needs libusb
                    scr = UsbRaw()
                    scr.init(brightness_param=self._brightness())
                    self._brightness_applied = self._brightness()
                    self.store.update_device(connected=True, last_error=None)
                    log.info("connected via libusb: %dx%d", scr.width, scr.height)

                tools = self.store.raw_tools()
                if not tools:  # first sample not in yet
                    self.stop_event.wait(0.5)
                    continue

                if scr is not None:
                    b = self._brightness()
                    if b != self._brightness_applied:
                        self._brightness_applied = b
                    scr.set_brightness(b)  # insurance against a stray dark frame
                frame = render(tools)
                self._push(scr, frame)

                ov = (self.store.get("attention") or {}).get("overlay")
                if ov and ov["started_at"] != self._last_overlay_start:
                    self._last_overlay_start = ov["started_at"]
                    log.info("playing overlay [%s]: %s", ov["kind"], ov["label"])
                    self._play_overlay(scr, frame, ov)
                else:
                    self.stop_event.wait(self.interval)
            except Exception as e:  # screen unplugged, USB hiccup, libusb missing...
                log.warning("%s; retrying in 3s", e)
                self.store.update_device(connected=False, last_error=str(e))
                try:
                    if scr is not None:
                        scr.close()
                except Exception:
                    pass
                scr = None
                self.stop_event.wait(3)
        if scr is not None:
            scr.close()
        self.store.update_device(connected=False)
