"""Stats providers for the code-display dashboard.

DummyStatsProvider ships first; live providers can replace it behind the
same interface (get_stats() -> list[ToolStats]).
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field


@dataclass
class SessionInfo:
    """One concurrent agent session (a Warp Claude Code window, a Codex thread)."""
    id: str
    label: str                 # working-directory name (cwd basename)
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    active: bool = False         # touched within ACTIVE_WINDOW (shown in list)
    last_active: float = 0.0     # epoch seconds
    live: bool = False           # writing within LIVE_WINDOW (agent working now)
    needs_input: bool = False    # Notification hook fired: awaiting the user
    attention_kind: str = ""     # "needs" (blocked on you) or "idle" (turn ended)


@dataclass
class ToolStats:
    name: str
    model: str
    sessions_today: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    activity_24h: list[float] = field(default_factory=list)  # 24 hourly buckets
    live: bool = False           # False => dummy data; True => real
    active: bool = False         # a session is running right now
    cost_estimated: bool = False  # cost derived from token pricing, not authoritative
    quota_pct: float | None = None        # subscription usage % (Codex weekly)
    quota_resets_at: float | None = None  # epoch seconds
    note: str = ""                        # short status shown when no metric (e.g. "paused")
    sessions: list["SessionInfo"] = field(default_factory=list)


class DummyStatsProvider:
    """Plausible, slowly-evolving fake numbers so the screen visibly updates."""

    def __init__(self) -> None:
        self.rng = random.Random(42)
        self.t0 = time.time()
        self.base = {
            "Claude Code": dict(sessions=7, tin=2_400_000, tout=310_000, cost=12.40),
            "Codex": dict(sessions=3, tin=880_000, tout=95_000, cost=4.15),
        }
        self.models = {"Claude Code": "fable-5.1", "Codex": "gpt-5-codex"}

    def _activity(self, seed: int) -> list[float]:
        rng = random.Random(seed + int(time.time() // 3600))
        hour = time.localtime().tm_hour
        out = []
        for h in range(24):
            # more activity in working hours, noise on top
            daylight = max(0.0, math.sin((h - 6) / 24 * math.pi * 2) + 0.4)
            recency = 1.4 if abs(h - hour) <= 2 else 1.0
            out.append(max(0.0, daylight * recency + rng.uniform(-0.25, 0.45)))
        return out

    def get_stats(self) -> list[ToolStats]:
        drift = (time.time() - self.t0) / 60.0  # minutes since start
        result = []
        for i, (name, b) in enumerate(self.base.items()):
            wobble = 1 + 0.002 * drift + self.rng.uniform(-0.001, 0.001)
            result.append(ToolStats(
                name=name,
                model=self.models[name],
                sessions_today=b["sessions"] + int(drift / 45) % 3,
                tokens_in=int(b["tin"] * wobble),
                tokens_out=int(b["tout"] * wobble),
                cost_usd=b["cost"] * wobble,
                activity_24h=self._activity(seed=i * 1000),
                live=False,
            ))
        return result
