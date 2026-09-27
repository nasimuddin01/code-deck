"""`source = "otel"`: agents that export OpenTelemetry metrics.

CODE DECK already runs an OTLP/HTTP (JSON) receiver for Claude Code on
127.0.0.1:4318 (CODE_DECK_OTLP_PORT). Any other agent that exports metrics
can send them there too; this source picks out its own by service name:

    [agents.my-agent]
    source = "otel"
    service = "my-agent"                 # resource attribute service.name
    cost_metric = "my_agent.cost.usage"  # optional, USD
    tokens_metric = "my_agent.token.usage"
    token_type_attr = "type"             # attribute whose value is "input" / "output"
    session_attr = "session.id"          # optional: per-session rows
    model_attr = "model"
    cwd_attr = "cwd"                     # optional

Delta and cumulative temporality are both handled. Today's totals persist
across restarts (~/.claude/code-deck/otel_<agent>.json). A session that
reported within two minutes is live.
"""
from __future__ import annotations

import datetime
import json
import os
import threading
import time
from typing import Any

from .. import config
from ..providers.otel_receiver import _dp_attrs, _dp_value
from ..providers.stats import SessionInfo, ToolStats
from .builtin import otel_receiver
from .payload import ACTIVE_WINDOW, LIVE_WINDOW
from .registry import SourceContext, register_source
from .spec import AgentSpec

CUMULATIVE = 2   # OTLP AggregationTemporality


def _resource_attrs(rm: dict) -> dict[str, str]:
    out = {}
    for a in (rm.get("resource") or {}).get("attributes", []):
        v = a.get("value", {})
        out[a.get("key", "")] = str(next(iter(v.values()))) if v else ""
    return out


class OtelSource:
    def __init__(self, spec: AgentSpec, ctx: SourceContext) -> None:
        o = spec.options
        self.spec = spec
        self.ctx = ctx
        self.service = str(o.get("service") or "")
        if not self.service:
            raise ValueError('otel source needs `service = "<service.name>"`')
        self.cost_metric = o.get("cost_metric")
        self.tokens_metric = o.get("tokens_metric")
        if not (self.cost_metric or self.tokens_metric):
            raise ValueError("otel source needs `cost_metric` and/or `tokens_metric`")
        self.type_attr = str(o.get("token_type_attr", "type"))
        self.session_attr = str(o.get("session_attr", "session.id"))
        self.model_attr = str(o.get("model_attr", "model"))
        self.cwd_attr = str(o.get("cwd_attr", "cwd"))
        self.path = config.STATE_DIR / f"otel_{spec.id}.json"
        self._lock = threading.Lock()
        self._day = datetime.date.today().isoformat()
        # session -> {"cost", "tin", "tout", "model", "cwd", "seen", "cum": {series: last}}
        self._sessions: dict[str, dict[str, Any]] = {}
        self._load()
        recv = otel_receiver(ctx)
        if recv is None:
            raise RuntimeError(f"OTLP port {config.OTLP_PORT} is busy; set CODE_DECK_OTLP_PORT")
        recv.listeners.append(self.ingest)

    # -- persistence -----------------------------------------------------------
    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text())
            if data.get("day") == self._day:
                self._sessions = data.get("sessions", {})
        except (OSError, ValueError, AttributeError):
            pass

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"day": self._day, "sessions": self._sessions}))
            os.replace(tmp, self.path)
        except OSError:
            pass

    # -- ingest ----------------------------------------------------------------
    def ingest(self, payload: dict) -> None:
        touched = False
        with self._lock:
            today = datetime.date.today().isoformat()
            if today != self._day:
                self._day, self._sessions = today, {}
            for rm in payload.get("resourceMetrics", []):
                if _resource_attrs(rm).get("service.name") != self.service:
                    continue
                for sm in rm.get("scopeMetrics", []):
                    for m in sm.get("metrics", []):
                        name = m.get("name")
                        if name not in (self.cost_metric, self.tokens_metric):
                            continue
                        body = m.get("sum") or m.get("gauge") or {}
                        cumulative = body.get("aggregationTemporality") == CUMULATIVE or "gauge" in m
                        for dp in body.get("dataPoints", []):
                            self._add(name, dp, cumulative)
                            touched = True
            if touched:
                self._save()
        if touched:
            self.ctx.wake()

    def _add(self, metric: str, dp: dict, cumulative: bool) -> None:
        attrs = _dp_attrs(dp)
        sid = attrs.get(self.session_attr) or "_"
        s = self._sessions.setdefault(sid, {"cost": 0.0, "tin": 0.0, "tout": 0.0,
                                            "model": "", "cwd": "", "seen": 0.0, "cum": {}})
        if metric == self.cost_metric:
            bucket = "cost"
        else:
            bucket = "tout" if attrs.get(self.type_attr) == "output" else "tin"
        val = _dp_value(dp)
        if cumulative:   # running total per series: add only the increase
            series = f"{bucket}|" + "|".join(f"{k}={v}" for k, v in sorted(attrs.items()))
            prev = s["cum"].get(series, 0.0)
            s["cum"][series] = val
            val = val - prev if val >= prev else val       # counter reset
        s[bucket] += val
        s["model"] = attrs.get(self.model_attr) or s["model"]
        s["cwd"] = attrs.get(self.cwd_attr) or s["cwd"]
        s["seen"] = time.time()

    # -- read --------------------------------------------------------------------
    def stats(self) -> ToolStats:
        now = time.time()
        with self._lock:
            items = [(k, dict(v)) for k, v in self._sessions.items()]
        sessions = []
        for sid, s in items:
            if sid == "_" or now - s["seen"] > ACTIVE_WINDOW:
                continue
            label = os.path.basename(s["cwd"].rstrip("/")) if s["cwd"] else sid[:8]
            sessions.append(SessionInfo(
                id=sid[:8] if len(sid) > 12 else sid, label=label, model=s["model"], cwd=s["cwd"],
                tokens_in=int(s["tin"]), tokens_out=int(s["tout"]), active=True,
                last_active=s["seen"], live=now - s["seen"] <= LIVE_WINDOW))
        sessions.sort(key=lambda x: (x.live, x.last_active), reverse=True)
        return ToolStats(
            name=self.spec.name, model=next((s["model"] for _, s in items if s["model"]), ""),
            sessions_today=sum(1 for sid, _ in items if sid != "_") or (1 if items else 0),
            tokens_in=int(sum(s["tin"] for _, s in items)), tokens_out=int(sum(s["tout"] for _, s in items)),
            cost_usd=sum(s["cost"] for _, s in items), live=True,
            active=any(s.live for s in sessions), sessions=sessions,
            note="" if items else "waiting for data")


register_source("otel", OtelSource)
