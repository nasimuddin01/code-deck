"""The one JSON shape every custom source speaks: `push` bodies, `command`
script output, and what `python` sources can build from.

Agent-level (all optional):

    {
      "model": "gpt-5",              # shown when no session has one
      "cost_usd": 3.20,              # today's spend; default: sum of sessions
      "tokens_in": 120000,           # today's totals; default: sum of sessions
      "tokens_out": 9000,
      "sessions_today": 4,           # default: number of sessions
      "quota_pct": 42,               # weekly/monthly quota used, 0-100
      "quota_resets_at": 1790000000, # epoch seconds
      "note": "paused",              # short text when there is no number to show
      "activity_24h": [0, 1, ...],   # 24 hourly buckets for the sparkline
      "cost_estimated": false,
      "sessions": [ <session>, ... ]
    }

Session:

    {
      "id": "abc123",                # required, unique per agent
      "label": "my-app",             # default: basename of cwd, else the id
      "cwd": "/path/to/my-app",
      "model": "gpt-5",
      "state": "working",            # working | waiting | done | idle
      "tokens_in": 1000, "tokens_out": 200, "cost_usd": 0.12,
      "last_active": 1790000000      # epoch seconds; default: now
    }

States: working = green "live"; waiting = blue "needs you" (plays the
banner); done = blue "turn ended"; idle = grey, shows how long ago.
Numbers are running totals, not deltas: send the latest value each time.
"""
from __future__ import annotations

import os
import time
from typing import Any

from ..providers.stats import SessionInfo, ToolStats

STATES = ("working", "waiting", "done", "idle")
ACTIVE_WINDOW = 20 * 60   # a session drops off the list after this long without news
LIVE_WINDOW = 120         # "working" older than this isn't shown as live (agent may be gone)


def _num(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _opt_num(v: Any) -> float | None:
    return None if v is None or v == "" else _num(v, 0.0)


def session_from(data: dict, now: float | None = None) -> SessionInfo:
    now = time.time() if now is None else now
    sid = str(data.get("id") or "").strip()
    if not sid:
        raise ValueError("session needs an id")
    cwd = str(data.get("cwd") or "")
    label = str(data.get("label") or (os.path.basename(cwd.rstrip("/")) if cwd else "") or sid)
    state = str(data.get("state") or "idle").lower()
    if state not in STATES:
        raise ValueError(f"state must be one of {', '.join(STATES)}")
    last = _num(data.get("last_active"), now) or now
    fresh = now - last
    return SessionInfo(
        id=sid[:8] if len(sid) > 12 else sid,
        label=label, model=str(data.get("model") or ""), cwd=cwd,
        tokens_in=int(_num(data.get("tokens_in"))), tokens_out=int(_num(data.get("tokens_out"))),
        active=fresh <= ACTIVE_WINDOW, last_active=last,
        live=state == "working" and fresh <= LIVE_WINDOW,
        needs_input=state in ("waiting", "done"),
        attention_kind="needs" if state == "waiting" else "idle" if state == "done" else "",
    )


def stats_from(name: str, data: dict, now: float | None = None) -> ToolStats:
    """ToolStats from an agent-level payload (sessions older than the active
    window are dropped)."""
    now = time.time() if now is None else now
    raw_sessions = data.get("sessions") or []
    if not isinstance(raw_sessions, list):
        raise ValueError("`sessions` must be a list")
    sessions = [s for s in (session_from(x, now) for x in raw_sessions if isinstance(x, dict)) if s.active]
    costs = [_num(x.get("cost_usd")) for x in raw_sessions if isinstance(x, dict)]
    sessions.sort(key=lambda s: (s.live, s.needs_input, s.last_active), reverse=True)
    model = str(data.get("model") or next((s.model for s in sessions if s.model), ""))
    activity = data.get("activity_24h") or []
    return ToolStats(
        name=name, model=model,
        sessions_today=int(_num(data.get("sessions_today"), len(sessions))),
        tokens_in=int(_num(data.get("tokens_in"), sum(s.tokens_in for s in sessions))),
        tokens_out=int(_num(data.get("tokens_out"), sum(s.tokens_out for s in sessions))),
        cost_usd=_num(data.get("cost_usd"), sum(costs)),
        activity_24h=[_num(v) for v in activity][:24] if isinstance(activity, list) else [],
        live=True, active=any(s.live for s in sessions),
        cost_estimated=bool(data.get("cost_estimated", False)),
        quota_pct=_opt_num(data.get("quota_pct")),
        quota_resets_at=_opt_num(data.get("quota_resets_at")),
        note=str(data.get("note") or ""),
        sessions=sessions,
    )
