"""Wire the pieces together for `code-deck serve` / `render`: store, samplers,
device loop and the HTTP app. Kept out of cli.py so tests and the one-shot
renderer can build a runtime without typer."""
from __future__ import annotations

import logging
import socket
import threading
import time

from .config import ensure_dirs
from .server.app import AppContext, create_app
from .server.layout import LayoutStore, Settings
from .state.attention import AttentionTracker
from .state.sampler import StatsSampler
from .state.store import StateStore
from .state.system import SystemSampler

log = logging.getLogger(__name__)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Runtime:
    def __init__(self, *, renderer: str, host: str = "127.0.0.1", port: int = 8765,
                 interval: float | None = None, brightness: int | None = None,
                 overlay: bool | None = None, overlay_seconds: float | None = None,
                 no_device: bool = False, mock: bool = False,
                 player_url: str | None = None) -> None:
        ensure_dirs()
        self.host, self.port = host, port
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

        self.sampler = StatsSampler(self.store, self.tracker, self.interval, self.stop, mock=mock)
        self.ctx.sampler = self.sampler
        self.threads: list[threading.Thread] = [self.sampler, SystemSampler(self.store, self.stop)]
        self.renderer_name = renderer
        if renderer == "pil":
            from .render.legacy_loop import PilDeviceLoop
            self.threads.append(PilDeviceLoop(self.store, self.stop,
                                              interval=self.interval, no_device=no_device))
        elif renderer == "chromium":
            from .render.chromium import ChromiumRenderer
            from .render.device_loop import DeviceLoop
            from .server.app import static_dir
            url = player_url or f"http://127.0.0.1:{port}/player?device=1"
            if player_url is None and static_dir() is None:
                raise ValueError("web app is not built (no static/index.html); "
                                 "run `pnpm build:server` in web/ or pass --player-url")
            self.threads.append(DeviceLoop(self.store, self.stop, ChromiumRenderer(url),
                                           no_device=no_device))
        elif renderer != "none":
            raise ValueError(f"unknown renderer {renderer!r} (pil | chromium | none)")

    def _on_settings(self, s: Settings) -> None:
        self.tracker.enabled = s.overlay_enabled
        self.tracker.seconds = s.overlay_seconds

    def start(self) -> None:
        for t in self.threads:
            t.start()

    def shutdown(self) -> None:
        self.stop.set()
        self.sampler.wake()
        for t in self.threads:
            t.join(timeout=8)

    # -- embedded HTTP server (for `render --once` and tests) ------------------
    def serve_in_thread(self):
        import uvicorn
        config = uvicorn.Config(self.app, host=self.host, port=self.port,
                                log_config=None, access_log=False)
        server = uvicorn.Server(config)
        t = threading.Thread(target=server.run, name="uvicorn", daemon=True)
        t.start()
        deadline = time.time() + 10
        while not server.started and time.time() < deadline:
            time.sleep(0.05)
        if not server.started:
            raise RuntimeError("HTTP server did not start")
        return server
