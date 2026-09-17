"""Background thread: host resource stats (psutil) with short histories."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque

import psutil

from .store import StateStore

log = logging.getLogger(__name__)
HISTORY = 60  # samples kept per metric (1 Hz -> one minute)


class SystemSampler(threading.Thread):
    def __init__(self, store: StateStore, stop: threading.Event, interval: float = 1.0) -> None:
        super().__init__(name="system-sampler", daemon=True)
        self.store = store
        self.stop_event = stop
        self.interval = interval
        self._hist = {k: deque(maxlen=HISTORY)
                      for k in ("cpu_pct", "mem_pct", "net_up_bps", "net_down_bps")}
        self._net_prev: tuple[float, int, int] | None = None
        psutil.cpu_percent(None)  # prime the non-blocking cpu counter

    def sample(self) -> dict:
        now = time.time()
        vm = psutil.virtual_memory()
        du = psutil.disk_usage("/")
        nio = psutil.net_io_counters()
        up = down = 0.0
        if self._net_prev is not None:
            t0, s0, r0 = self._net_prev
            dt = max(now - t0, 1e-6)
            up = max(0.0, (nio.bytes_sent - s0) / dt)
            down = max(0.0, (nio.bytes_recv - r0) / dt)
        self._net_prev = (now, nio.bytes_sent, nio.bytes_recv)

        cur = {
            "cpu_pct": psutil.cpu_percent(None),
            "mem_pct": vm.percent, "mem_used": vm.used, "mem_total": vm.total,
            "disk_pct": du.percent, "disk_used": du.used, "disk_total": du.total,
            "net_up_bps": up, "net_down_bps": down,
        }
        for k, dq in self._hist.items():
            dq.append(round(cur[k], 2))
        cur["history"] = {k: list(dq) for k, dq in self._hist.items()}
        return cur

    def run(self) -> None:
        while True:
            try:
                self.store.publish("system", self.sample())
            except Exception:
                log.exception("system sampler failed")
            if self.stop_event.wait(self.interval):
                return
