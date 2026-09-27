"""`source = "push"`: agents report their own status over HTTP.

    POST   /api/agents/<agent>                      agent-level fields (+ optional sessions list)
    POST   /api/agents/<agent>/sessions/<session>   create/update one session
    DELETE /api/agents/<agent>/sessions/<session>   session finished, remove it

Bodies use the shape in payload.py. `code-deck push` wraps these for shell
scripts and hooks. Pushing to an id nobody declared creates the agent on the
fly (auto colour, name = id); declare it in agents.toml to name and colour it.

State survives a server restart (~/.claude/code-deck/push_state.json);
sessions without news for 20 minutes drop off.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from .. import config
from .payload import ACTIVE_WINDOW, stats_from
from .registry import SourceContext, register_source
from .spec import AgentSpec

STATE_PATH = config.STATE_DIR / "push_state.json"
AGENT_FIELDS = ("model", "cost_usd", "tokens_in", "tokens_out", "sessions_today", "quota_pct",
                "quota_resets_at", "note", "activity_24h", "cost_estimated")
SESSION_FIELDS = ("label", "cwd", "model", "state", "tokens_in", "tokens_out", "cost_usd", "last_active")


class PushHub:
    """Thread-safe store of everything pushed, keyed by agent id."""

    def __init__(self, path=STATE_PATH) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._agents: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text())
            if isinstance(data, dict):
                self._agents = {k: v for k, v in data.items() if isinstance(v, dict)}
        except (OSError, ValueError):
            self._agents = {}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._agents))
            os.replace(tmp, self.path)
        except OSError:
            pass   # best-effort, never break a push

    def _agent(self, agent_id: str) -> dict[str, Any]:
        return self._agents.setdefault(agent_id, {"fields": {}, "sessions": {}})

    def update_agent(self, agent_id: str, fields: dict[str, Any], sessions: list[dict] | None = None) -> None:
        now = time.time()
        with self._lock:
            a = self._agent(agent_id)
            a["fields"].update({k: v for k, v in fields.items() if k in AGENT_FIELDS and v is not None})
            if sessions is not None:           # a full list replaces what we had
                a["sessions"] = {}
                for s in sessions:
                    sid = str(s.get("id") or "")
                    if sid:
                        a["sessions"][sid] = self._clean_session(s, now)
            self._save()

    def upsert_session(self, agent_id: str, session_id: str, fields: dict[str, Any]) -> None:
        now = time.time()
        with self._lock:
            sess = self._agent(agent_id)["sessions"]
            cur = sess.get(session_id, {})
            cur.update(self._clean_session(fields, now))
            sess[session_id] = cur
            self._save()

    def end_session(self, agent_id: str, session_id: str) -> bool:
        with self._lock:
            gone = self._agent(agent_id)["sessions"].pop(session_id, None) is not None
            self._save()
            return gone

    @staticmethod
    def _clean_session(fields: dict[str, Any], now: float) -> dict[str, Any]:
        out = {k: v for k, v in fields.items() if k in SESSION_FIELDS and v is not None}
        out.setdefault("last_active", now)   # every push counts as news
        return out

    def payload(self, agent_id: str) -> dict[str, Any]:
        """The agent's data in payload.py shape, stale sessions pruned."""
        now = time.time()
        with self._lock:
            a = self._agents.get(agent_id)
            if not a:
                return {}
            stale = [k for k, s in a["sessions"].items() if now - float(s.get("last_active", 0)) > ACTIVE_WINDOW]
            for k in stale:
                del a["sessions"][k]
            if stale:
                self._save()
            return {**a["fields"], "sessions": [{"id": k, **v} for k, v in a["sessions"].items()]}


def push_hub(ctx: SourceContext) -> PushHub:
    return ctx.service("push", PushHub)


class PushSource:
    def __init__(self, spec: AgentSpec, ctx: SourceContext) -> None:
        self.spec = spec
        self.hub = push_hub(ctx)

    def stats(self):
        data = self.hub.payload(self.spec.id)
        st = stats_from(self.spec.name, data)
        if not data:
            st.live = False
            st.note = st.note or "waiting for data"
        return st


register_source("push", PushSource)
