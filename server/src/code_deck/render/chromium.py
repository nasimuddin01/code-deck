"""Render the React player with headless Chromium (Playwright) and hand frames
to the device loop.

The page keeps `window.__cd = {ready, dirty, rev}`; anything that changes
pixels bumps `dirty`. We poll that counter (cheap) and screenshot only when it
moved, plus a heartbeat screenshot so nothing is ever missed. Uses the
Playwright *sync* API, so this object must live on a plain thread (the device
loop), never on the asyncio loop.
"""
from __future__ import annotations

import io
import logging
import threading
import time

from PIL import Image

from .base import H, W

log = logging.getLogger(__name__)

LAUNCH_ARGS = [
    "--disable-lcd-text",            # no subpixel AA: identical on any host
    "--font-render-hinting=none",
    "--force-color-profile=srgb",
    "--disable-gpu",
    "--hide-scrollbars",
    "--renderer-process-limit=1",
]
DIRTY_POLL_S = 0.1
HEARTBEAT_S = 5.0
READY_TIMEOUT_MS = 20_000
RSS_LIMIT_MB = 600


class ChromiumRenderer:
    name = "chromium"

    def __init__(self, player_url: str) -> None:
        self.player_url = player_url
        self._pw = None
        self._browser = None
        self._page = None
        self._dirty_seen = -1
        self._last_shot = 0.0
        self._backoff = 1.0
        self._crashed = threading.Event()
        self._last_rss_check = 0.0

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._launch()

    def _launch(self) -> None:
        self._crashed.clear()
        self._browser = self._pw.chromium.launch(headless=True, args=LAUNCH_ARGS)
        self._browser.on("disconnected", lambda *_: self._crashed.set())
        ctx = self._browser.new_context(viewport={"width": W, "height": H},
                                        device_scale_factor=1, color_scheme="dark")
        self._page = ctx.new_page()
        self._page.on("crash", lambda *_: self._crashed.set())
        self._page.goto(self.player_url, wait_until="domcontentloaded")
        self._page.wait_for_function("() => window.__cd && window.__cd.ready",
                                     timeout=READY_TIMEOUT_MS)
        self._dirty_seen = -1  # force a first frame
        self._backoff = 1.0
        log.info("chromium ready on %s", self.player_url)

    def _relaunch(self) -> None:
        log.warning("chromium gone; relaunching in %.0fs", self._backoff)
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        time.sleep(self._backoff)
        self._backoff = min(self._backoff * 2, 30.0)
        self._launch()

    def stop(self) -> None:
        for closer in (lambda: self._browser and self._browser.close(),
                       lambda: self._pw and self._pw.stop()):
            try:
                closer()
            except Exception:
                pass

    # -- frames -------------------------------------------------------------
    def _rss_ok(self) -> bool:
        now = time.time()
        if now - self._last_rss_check < 60:
            return True
        self._last_rss_check = now
        try:
            import psutil
            total = 0
            for p in psutil.process_iter(["name", "memory_info", "cmdline"]):
                cmd = " ".join(p.info.get("cmdline") or [])
                if "chrom" in (p.info.get("name") or "").lower() and "--headless" in cmd:
                    total += p.info["memory_info"].rss
            mb = total / 1_048_576
            if mb > RSS_LIMIT_MB:
                log.warning("headless chromium using %.0f MB; restarting", mb)
                return False
        except Exception:
            pass
        return True

    def _dirty(self) -> int:
        return int(self._page.evaluate("() => (window.__cd ? window.__cd.dirty : -1)"))

    def _screenshot(self) -> Image.Image:
        png = self._page.screenshot(type="png", animations="allow", caret="hide", scale="css")
        return Image.open(io.BytesIO(png)).convert("RGB")

    def poll(self, timeout: float) -> Image.Image | None:
        deadline = time.time() + timeout
        while True:
            if self._crashed.is_set() or not self._rss_ok():
                self._relaunch()
                return self._take()
            try:
                d = self._dirty()
            except Exception as e:  # page navigated/crashed between checks
                log.warning("dirty poll failed: %s", e)
                self._crashed.set()
                continue
            now = time.time()
            if d != self._dirty_seen or now - self._last_shot >= HEARTBEAT_S:
                self._dirty_seen = d
                return self._take()
            if now >= deadline:
                return None
            time.sleep(min(DIRTY_POLL_S, max(0.0, deadline - now)))

    def _take(self) -> Image.Image:
        img = self._screenshot()
        self._last_shot = time.time()
        return img
