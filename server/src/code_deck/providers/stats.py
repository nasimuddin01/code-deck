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
    cwd: str = ""                # full working directory when known
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
    sessions: list[SessionInfo] = field(default_factory=list)


class DummyStatsProvider:
    """Plausible, slowly-evolving fake numbers so the screen visibly updates."""

    def __init__(self) -> None:
        self.rng = random.Random(42)
        self.t0 = time.time()
        self.base = {
            "Claude Code": {"sessions": 7, "tin": 2_400_000, "tout": 310_000, "cost": 12.40},
            "Codex": {"sessions": 3, "tin": 880_000, "tout": 95_000, "cost": 4.15},
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

    def _sessions(self, name: str, now: float) -> list[SessionInfo]:
        # invented example projects: screenshots and demos show every row state
        if name == "Claude Code":
            return [
                SessionInfo(id="a1b2c3d4", label="my-app", model="fable-5.1", cwd="~/code/my-app",
                            tokens_in=1_420_000, tokens_out=182_000, active=True,
                            last_active=now - 4, live=True),
                SessionInfo(id="e5f6a7b8", label="api-server", model="fable-5.1", cwd="~/code/api-server",
                            tokens_in=610_000, tokens_out=77_000, active=True,
                            last_active=now - 95, needs_input=True, attention_kind="needs"),
                SessionInfo(id="c9d0e1f2", label="docs-site", model="sonnet-5", cwd="~/code/docs-site",
                            tokens_in=240_000, tokens_out=31_000, active=True,
                            last_active=now - 540),
            ]
        if name == "Codex":
            return [SessionInfo(id="0a1b2c3d", label="codex", model="gpt-5-codex",
                                tokens_in=880_000, tokens_out=95_000, active=True,
                                last_active=now - 1260)]
        return []

    def get_stats(self) -> list[ToolStats]:
        now = time.time()
        drift = (now - self.t0) / 60.0  # minutes since start
        result = []
        for i, (name, b) in enumerate(self.base.items()):
            wobble = 1 + 0.002 * drift + self.rng.uniform(-0.001, 0.001)
            sessions = self._sessions(name, now)
            result.append(ToolStats(
                name=name,
                model=self.models[name],
                sessions_today=b["sessions"] + int(drift / 45) % 3,
                tokens_in=int(b["tin"] * wobble),
                tokens_out=int(b["tout"] * wobble),
                cost_usd=b["cost"] * wobble,
                activity_24h=self._activity(seed=i * 1000),
                live=False,
                active=any(x.live for x in sessions),
                quota_pct=42.0 if name == "Codex" else None,
                quota_resets_at=now + 3 * 86400 if name == "Codex" else None,
                sessions=sessions,
            ))
        result.insert(1, ToolStats(
            name="Claude Max", model="", sessions_today=0, tokens_in=0, tokens_out=0,
            cost_usd=0.0, live=False, quota_pct=63.0, quota_resets_at=now + 2 * 86400))
        return result
