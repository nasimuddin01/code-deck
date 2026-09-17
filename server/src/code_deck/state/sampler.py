"""Background thread: poll the live providers into the StateStore.

`LiveStatsProvider.get_stats()` is synchronous and touches the filesystem and
the Codex app-server, so it must never run on the asyncio loop. The
AttentionTracker lives here too: the overlay decision is made once, server-side,
and every renderer just reads `attention.overlay`.
"""
from __future__ import annotations

import dataclasses
import logging
import threading
import time

from ..providers.live import LiveStatsProvider
from ..providers.stats import DummyStatsProvider
from .attention import AttentionTracker
from .store import StateStore

log = logging.getLogger(__name__)


class StatsSampler(threading.Thread):
    def __init__(self, store: StateStore, tracker: AttentionTracker, interval: float,
                 stop: threading.Event) -> None:
        super().__init__(name="stats-sampler", daemon=True)
        self.store = store
        self.tracker = tracker
        self.interval = interval
        self.stop_event = stop
        self.live = LiveStatsProvider()
        self.fallback = DummyStatsProvider()

    def _stats(self):
        try:
            return self.live.get_stats()
        except Exception as e:  # never let a parse hiccup blank the screen
            log.warning("live stats failed (%s); using dummy", e)
            return self.fallback.get_stats()

    def tick(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        stats = self._stats()
        self.store.set_raw_tools(stats)
        self.store.publish("tools", [dataclasses.asdict(t) for t in stats])
        started = self.tracker.update(stats, now)
        for ov in started:
            log.info("overlay [%s]: %s", ov.kind, ov.label)
        cur = self.tracker.current
        self.store.publish("attention",
                           {"overlay": dataclasses.asdict(cur) if cur else None})

    def run(self) -> None:
        while True:
            try:
                self.tick()
            except Exception:
                log.exception("stats sampler tick failed")
            if self.stop_event.wait(self.interval):
                return
