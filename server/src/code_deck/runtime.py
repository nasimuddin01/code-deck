"""Wire the pieces together for `code-deck serve`: store, samplers, device
loop and the HTTP server. Kept out of cli.py so tests can build a runtime
without typer."""
from __future__ import annotations

import logging
import threading

from .config import ensure_dirs
from .server.app import AppContext, create_app
from .server.layout import LayoutStore, Settings
from .state.attention import AttentionTracker
from .state.sampler import StatsSampler
from .state.store import StateStore
from .state.system import SystemSampler

log = logging.getLogger(__name__)


class Runtime:
    def __init__(self, *, renderer: str, interval: float | None, brightness: int | None,
                 overlay: bool | None, overlay_seconds: float | None,
                 no_device: bool = False) -> None:
        ensure_dirs()
        self.stop = threading.Event()
        self.store = StateStore()
        self.layouts = LayoutStore()
        s = self.layouts.load().settings
        # precedence: CLI flag > layout settings > defaults
        self.interval = interval if interval is not None else s.refresh_seconds
        self.tracker = AttentionTracker(
            enabled=overlay if overlay is not None else s.overlay_enabled,
            seconds=overlay_seconds if overlay_seconds is not None else s.overlay_seconds)
        self.store.update_device(brightness=brightness if brightness is not None else s.brightness)

        self.ctx = AppContext(store=self.store, layouts=self.layouts)
        self.ctx.settings_listeners.append(self._on_settings)
        self.app = create_app(self.ctx)

        self.threads: list[threading.Thread] = [
            StatsSampler(self.store, self.tracker, self.interval, self.stop),
            SystemSampler(self.store, self.stop),
        ]
        if renderer == "pil":
            from .render.legacy_loop import PilDeviceLoop
            self.threads.append(PilDeviceLoop(self.store, self.stop,
                                              interval=self.interval, no_device=no_device))
        elif renderer != "none":
            raise ValueError(f"renderer {renderer!r} is not available yet")

    def _on_settings(self, s: Settings) -> None:
        self.tracker.enabled = s.overlay_enabled
        self.tracker.seconds = s.overlay_seconds

    def start(self) -> None:
        for t in self.threads:
            t.start()

    def shutdown(self) -> None:
        self.stop.set()
        for t in self.threads:
            t.join(timeout=5)
