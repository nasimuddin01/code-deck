"""Decide when a session's "needs you" should raise the full-screen overlay.

Ported from the original run_dashboard loop so it can be unit-tested and shared
by every renderer. Each poll, sessions flagged `needs_input` are keyed by
(session id, kind). A key not present on the previous poll is *new*. Only a
new key whose kind is not "idle" starts an overlay: "needs" (permission prompt
or question) is a real block on the user; "idle" (turn ended) is a row status
only. Keying on kind means an idle -> needs transition re-announces.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Overlay:
    session_id: str
    label: str
    kind: str
    started_at: float
    seconds: float

    def active(self, now: float) -> bool:
        return now - self.started_at < self.seconds


class AttentionTracker:
    def __init__(self, enabled: bool = True, seconds: float = 10.0) -> None:
        self.enabled = enabled
        self.seconds = float(seconds)
        self.current: Overlay | None = None
        self._announced: set[tuple[str, str]] = set()

    def update(self, tools, now: float) -> list[Overlay]:
        """Feed one poll of ToolStats; returns overlays that started this poll
        (at most one is made `current`). `current` self-clears after `seconds`."""
        needs: dict[tuple[str, str], str] = {}
        for st in tools:
            for s in st.sessions:
                if s.needs_input:
                    needs[(s.id, s.attention_kind or "needs")] = s.label
        new = [k for k in needs if k not in self._announced]
        self._announced = set(needs)

        if self.current is not None and not self.current.active(now):
            self.current = None

        started: list[Overlay] = []
        if self.enabled:
            for sid, kind in new:
                if kind == "idle":
                    continue
                started.append(Overlay(sid, needs[(sid, kind)], kind, now, self.seconds))
        if started:
            self.current = started[0]
        return started
