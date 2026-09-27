"""Background thread: poll the agent registry into the StateStore.

`AgentRegistry.get_stats()` is synchronous and touches the filesystem, the
Codex app-server and user scripts, so it must never run on the asyncio loop. The
AttentionTracker lives here too: the overlay decision is made once, server-side,
and every renderer just reads `attention.overlay`.
"""
from __future__ import annotations

import dataclasses
import logging
import threading
import time

from ..agents import AgentRegistry, load_specs
from ..agents.registry import SourceContext
from ..agents.spec import builtin_specs
from ..providers.stats import DummyStatsProvider
from .attention import AttentionTracker
from .store import StateStore

log = logging.getLogger(__name__)


class StatsSampler(threading.Thread):
    def __init__(self, store: StateStore, tracker: AttentionTracker, interval: float,
                 stop: threading.Event, mock: bool = False) -> None:
        super().__init__(name="stats-sampler", daemon=True)
        self.store = store
        self.tracker = tracker
        self.interval = interval
        self.stop_event = stop
        self._wake = threading.Event()
        # mock: dummy numbers only (golden renders, CI, machines without Claude/Codex)
        self.registry: AgentRegistry | None = None
        if not mock:
            specs, errors = load_specs()
            self.registry = AgentRegistry(specs, SourceContext(wake=self.wake), errors)
        self.fallback = DummyStatsProvider()

    def wake(self) -> None:
        """Tick now instead of at the next interval (a push just arrived)."""
        self._wake.set()

    def _mock_stats(self):
        colors = {s.name: s for s in builtin_specs()}
        stats = self.fallback.get_stats()
        for t in stats:
            if t.name in colors:
                t.agent_id, t.color, t.source = colors[t.name].id, colors[t.name].color, "mock"
        return stats

    def _stats(self):
        if self.registry is None:
            return self._mock_stats()
        try:
            return self.registry.get_stats()
        except Exception as e:  # never let a parse hiccup blank the screen
            log.warning("agent stats failed (%s); using dummy", e)
            return self._mock_stats()

    def agents(self) -> list[dict]:
        if self.registry is None:
            return [{**s.public(), "error": ""} for s in builtin_specs()]
        return self.registry.agents()

    def tick(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        stats = self._stats()
        self.store.set_raw_tools(stats)
        self.store.publish("tools", [dataclasses.asdict(t) for t in stats])
        self.store.publish("agents", self.agents())
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
            self._wake.wait(self.interval)
            self._wake.clear()
            if self.stop_event.is_set():
                return
