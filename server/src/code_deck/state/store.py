"""Thread-safe in-memory state shared by samplers, the device loop and the API.

Sections: tools (list of ToolStats as dicts), system, attention, device,
layout_rev. `publish()` only bumps `rev` when a section actually changes, so
WebSocket clients and the device loop can block on `wait_for_change()` instead
of polling. The raw ToolStats objects are kept alongside for the PIL renderer.
"""
from __future__ import annotations

import copy
import threading
import time
from collections.abc import Callable
from typing import Any


class StateStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._data: dict[str, Any] = {
            "tools": [],
            "agents": [],
            "system": None,
            "attention": {"overlay": None},
            "device": {
                "connected": False, "renderer": None, "brightness": None,
                "last_push_ms": None, "last_rect": None, "frames_pushed": 0,
                "last_error": None, "chromium_ok": None,
            },
            "layout_rev": 0,
        }
        self._raw_tools: list = []
        self.rev = 0
        self._listeners: list[Callable[[int], None]] = []

    # -- writes -------------------------------------------------------------
    def publish(self, section: str, value: Any) -> bool:
        """Replace a section; returns True (and bumps rev) only if it changed."""
        with self._lock:
            if section in self._data and self._data[section] == value:
                return False
            self._data[section] = copy.deepcopy(value)
            self.rev += 1
            self._cond.notify_all()
            listeners = list(self._listeners)
        for cb in listeners:
            cb(self.rev)
        return True

    def update_device(self, **fields: Any) -> bool:
        with self._lock:
            dev = dict(self._data["device"])
            dev.update(fields)
            return self.publish("device", dev)

    def set_raw_tools(self, tools: list) -> None:
        with self._lock:
            self._raw_tools = tools

    def add_listener(self, cb: Callable[[int], None]) -> None:
        with self._lock:
            self._listeners.append(cb)

    # -- reads --------------------------------------------------------------
    def get(self, section: str) -> Any:
        with self._lock:
            return copy.deepcopy(self._data.get(section))

    def raw_tools(self) -> list:
        with self._lock:
            return self._raw_tools

    def snapshot(self) -> dict:
        with self._lock:
            snap = copy.deepcopy(self._data)
            snap["rev"] = self.rev
            snap["ts"] = time.time()
            return snap

    def wait_for_change(self, last_rev: int, timeout: float) -> bool:
        """Block until rev != last_rev or timeout; True if changed."""
        with self._cond:
            return self._cond.wait_for(lambda: self.rev != last_rev, timeout=timeout)
