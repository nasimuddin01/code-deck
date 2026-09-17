"""Generic device loop: renderer frames -> dirty rect -> USB pushes.

Owns the USB device. "Latest frame wins": there is no queue, so after a slow
push the next poll simply picks up the newest picture. A change covering more
than FULL_FRACTION of the screen is pushed as a full frame (partial pushes
cost the same per pixel; the full path is just simpler).
"""
from __future__ import annotations

import logging
import threading
import time

from PIL import Image

from ..config import PREVIEW_PATH, ensure_dirs
from ..state.store import StateStore
from . import frame_diff
from .base import H, W, Renderer

log = logging.getLogger(__name__)
FULL_FRACTION = 0.60


class DeviceLoop(threading.Thread):
    def __init__(self, store: StateStore, stop: threading.Event, renderer: Renderer, *,
                 no_device: bool = False, preview: bool = True) -> None:
        super().__init__(name="device-loop", daemon=True)
        self.store = store
        self.stop_event = stop
        self.renderer = renderer
        self.no_device = no_device
        self.preview = preview
        self._last: Image.Image | None = None
        self._brightness_applied: int | None = None
        self._force_full = True

    def _brightness(self) -> int:
        b = self.store.get("device").get("brightness")
        return 39 if b is None else int(b)

    def _push(self, scr, frame: Image.Image) -> None:
        t0 = time.time()
        rect = [0, 0, W, H]
        if self._last is None or self._force_full:
            if scr is not None:
                scr.draw(frame)
        else:
            box = frame_diff.bbox(self._last, frame)
            if box is None:
                return
            if frame_diff.area(box) > FULL_FRACTION * W * H:
                if scr is not None:
                    scr.draw(frame)
            else:
                x0, y0, x1, y1 = box
                rect = [x0, y0, x1 - x0, y1 - y0]
                if scr is not None:
                    scr.draw(frame.crop(box), x0, y0)
        self._last = frame
        self._force_full = False
        if self.preview:
            try:
                frame.save(PREVIEW_PATH)
            except OSError:
                pass
        self.store.update_device(
            last_push_ms=int((time.time() - t0) * 1000), last_rect=rect,
            frames_pushed=self.store.get("device")["frames_pushed"] + 1)
        log.debug("pushed %s in %dms", rect, int((time.time() - t0) * 1000))

    def run(self) -> None:
        ensure_dirs()
        self.store.update_device(renderer=self.renderer.name, chromium_ok=None)
        scr = None
        try:
            self.renderer.start()
            self.store.update_device(chromium_ok=True)
        except Exception as e:
            log.error("renderer failed to start: %s", e)
            self.store.update_device(chromium_ok=False, last_error=str(e))
            return
        while not self.stop_event.is_set():
            try:
                if scr is None and not self.no_device:
                    from ..turzx.usbraw import UsbRaw  # lazy: needs libusb
                    scr = UsbRaw()
                    scr.init(brightness_param=self._brightness())
                    self._brightness_applied = self._brightness()
                    self._force_full = True
                    self.store.update_device(connected=True, last_error=None)
                    log.info("connected via libusb: %dx%d", scr.width, scr.height)

                frame = self.renderer.poll(timeout=0.5)
                if frame is None:
                    continue
                if scr is not None:
                    b = self._brightness()
                    if b != self._brightness_applied:
                        scr.set_brightness(b)
                        self._brightness_applied = b
                self._push(scr, frame)
            except Exception as e:  # USB hiccup, unplug, libusb missing...
                log.warning("%s; retrying in 3s", e)
                self.store.update_device(connected=False, last_error=str(e))
                try:
                    if scr is not None:
                        scr.close()
                except Exception:
                    pass
                scr = None
                self._force_full = True
                self.stop_event.wait(3)
        if scr is not None:
            scr.close()
        self.renderer.stop()
        self.store.update_device(connected=False)
