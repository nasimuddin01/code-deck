"""`source = "command"`: run a script on a timer and read its JSON.

    [agents.my-agent]
    source = "command"
    command = "~/bin/my-agent-usage --json"   # a string runs through /bin/sh; a list runs directly
    interval = 30                             # seconds between runs (min 2, default 30)
    timeout = 10                              # seconds before a run is killed (default 10)

The script prints one JSON object in the payload.py shape (agent totals and
an optional `sessions` list) and exits 0. Anything else marks the card
"error" and `code-deck agents list` shows why. The script runs in its own
thread, so a slow one never delays the other agents.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time

from .payload import stats_from
from .registry import SourceContext, register_source
from .spec import AgentSpec

log = logging.getLogger(__name__)


class CommandSource:
    def __init__(self, spec: AgentSpec, ctx: SourceContext) -> None:
        cmd = spec.options.get("command")
        if not cmd or not isinstance(cmd, (str, list)):
            raise ValueError('command source needs `command = "..."` (a string or a list)')
        self.spec = spec
        self.ctx = ctx
        self.shell = isinstance(cmd, str)
        self.cmd = os.path.expanduser(cmd) if self.shell else [os.path.expanduser(str(c)) for c in cmd]
        self.interval = max(2.0, float(spec.options.get("interval", 30)))
        self.timeout = max(1.0, float(spec.options.get("timeout", 10)))
        self._lock = threading.Lock()
        self._data: dict | None = None
        self._error = "not run yet"
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name=f"agent-{spec.id}", daemon=True)
        self._thread.start()

    def run_once(self) -> None:
        try:
            p = subprocess.run(self.cmd, shell=self.shell, capture_output=True, text=True,
                               timeout=self.timeout)
            if p.returncode != 0:
                raise RuntimeError(f"exit {p.returncode}: {(p.stderr or p.stdout).strip()[:200]}")
            data = json.loads(p.stdout)
            if not isinstance(data, dict):
                raise ValueError("output must be a JSON object")
            stats_from(self.spec.name, data)         # validate now, not at render time
        except subprocess.TimeoutExpired:
            self._set(None, f"timed out after {self.timeout:g}s")
        except (OSError, ValueError, RuntimeError) as e:
            self._set(None, str(e))
        else:
            self._set(data, "")

    def _set(self, data: dict | None, error: str) -> None:
        with self._lock:
            changed = data != self._data or error != self._error
            if data is not None:
                self._data = data
            self._error = error
        if error:
            log.warning("agent %s: %s", self.spec.id, error)
        if changed:
            self.ctx.wake()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            self._stop.wait(self.interval)

    def stats(self):
        with self._lock:
            data, error = self._data, self._error
        if error and data is None:
            raise RuntimeError(error)
        st = stats_from(self.spec.name, data or {}, time.time())
        if error:                                    # keep the last good numbers, flag it
            st.note = "stale"
        return st

    def close(self) -> None:
        self._stop.set()


register_source("command", CommandSource)
