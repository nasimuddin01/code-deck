"""In-process OTLP/HTTP receiver for authoritative Claude Code cost.

Claude Code (with CLAUDE_CODE_ENABLE_TELEMETRY=1) exports OTLP metrics over
http/json to /v1/metrics. We run a tiny threaded HTTP server inside the
dashboard process and accumulate the authoritative `claude_code.cost.usage`
(USD) and `claude_code.token.usage` per session.id — which equals the
transcript filename UUID, so the live provider can merge these onto its
per-session list, replacing the token-price estimate with real dollars.

Metrics are DELTA temporality (aggregationTemporality=1): each export is the
increment since the last one, so we sum. State resets at local midnight.

Enable globally by adding to ~/.claude/settings.json "env":
  CLAUDE_CODE_ENABLE_TELEMETRY=1
  OTEL_METRICS_EXPORTER=otlp
  OTEL_EXPORTER_OTLP_PROTOCOL=http/json
  OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
"""
from __future__ import annotations

import datetime
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import config

DEFAULT_PORT = config.OTLP_PORT
# survive runner restarts: without this, every restart wiped the day's
# accumulated cost and the $ hero visibly "reset" mid-day
STATE_PATH = str(config.OTEL_STATE_PATH)


def _dp_value(dp: dict) -> float:
    if "asDouble" in dp:
        return float(dp["asDouble"])
    if "asInt" in dp:
        return float(dp["asInt"])
    return 0.0


def _dp_attrs(dp: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for a in dp.get("attributes", []):
        v = a.get("value", {})
        # OTLP any-value: take the single contained scalar
        out[a["key"]] = str(next(iter(v.values()))) if v else ""
    return out


class OtelReceiver:
    """Accumulates today's Claude Code cost/tokens per session, thread-safe."""

    def __init__(self, port: int = DEFAULT_PORT) -> None:
        self.port = port
        self._lock = threading.Lock()
        self._day = datetime.date.today()
        # session_id -> {"cost": float, "tin": float, "tout": float, "model": str}
        self._sessions: dict[str, dict] = {}
        self._srv: ThreadingHTTPServer | None = None
        # extra consumers of every OTLP payload (`otel` agents), called after ingest
        self.listeners: list = []
        self._load()

    # -- persistence (lock held by callers where it matters) -----------------
    def _load(self) -> None:
        try:
            with open(STATE_PATH) as f:
                st = json.load(f)
            if st.get("day") == self._day.isoformat():
                self._sessions = {
                    sid: {"cost": float(s.get("cost", 0.0)),
                          "tin": float(s.get("tin", 0.0)),
                          "tout": float(s.get("tout", 0.0)),
                          "model": str(s.get("model", ""))}
                    for sid, s in st.get("sessions", {}).items()
                }
        except (OSError, ValueError):
            pass  # no/corrupt state -> start fresh

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
            tmp = STATE_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"day": self._day.isoformat(),
                           "sessions": self._sessions}, f)
            os.replace(tmp, STATE_PATH)
        except OSError:
            pass  # persistence is best-effort; never break ingest

    # -- ingest -------------------------------------------------------------
    def _roll_day(self) -> None:
        today = datetime.date.today()
        if today != self._day:
            self._day = today
            self._sessions.clear()
            self._save()

    def ingest(self, payload: dict) -> None:
        with self._lock:
            self._roll_day()
            for rm in payload.get("resourceMetrics", []):
                for sm in rm.get("scopeMetrics", []):
                    for m in sm.get("metrics", []):
                        name = m.get("name")
                        dps = (m.get("sum") or m.get("gauge") or {}).get("dataPoints", [])
                        if name == "claude_code.cost.usage":
                            for dp in dps:
                                self._add(dp, "cost", _dp_value(dp))
                        elif name == "claude_code.token.usage":
                            for dp in dps:
                                attrs = _dp_attrs(dp)
                                bucket = "tout" if attrs.get("type") == "output" else "tin"
                                self._add(dp, bucket, _dp_value(dp), attrs)
            self._save()
        for cb in list(self.listeners):
            try:
                cb(payload)
            except Exception:
                pass   # a broken agent source must not break Claude Code cost

    def _add(self, dp: dict, field: str, val: float, attrs: dict | None = None) -> None:
        attrs = attrs or _dp_attrs(dp)
        sid = attrs.get("session.id")
        if not sid:
            return
        s = self._sessions.setdefault(sid, {"cost": 0.0, "tin": 0.0, "tout": 0.0, "model": ""})
        s[field] += val
        if attrs.get("model"):
            s["model"] = attrs["model"]

    # -- reads --------------------------------------------------------------
    def cost_for(self, session_id: str) -> float | None:
        with self._lock:
            self._roll_day()
            s = self._sessions.get(session_id)
            return s["cost"] if s else None

    def tokens_for(self, session_id: str) -> tuple[int, int] | None:
        with self._lock:
            self._roll_day()
            s = self._sessions.get(session_id)
            return (int(s["tin"]), int(s["tout"])) if s else None

    def total_cost_today(self) -> float:
        with self._lock:
            self._roll_day()
            return sum(s["cost"] for s in self._sessions.values())

    def has_data(self) -> bool:
        with self._lock:
            return bool(self._sessions)

    # -- server -------------------------------------------------------------
    def start(self) -> OtelReceiver:
        recv = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silence access logs
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0) or 0)
                body = self.rfile.read(n) if n else b""
                try:
                    recv.ingest(json.loads(body))
                except Exception:
                    pass
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"{}")

        # loopback by default; Docker sets CODE_DECK_OTLP_HOST=0.0.0.0 so the
        # published port reaches the receiver
        host = config.OTLP_HOST
        self._srv = ThreadingHTTPServer((host, self.port), Handler)
        t = threading.Thread(target=self._srv.serve_forever, daemon=True)
        t.start()
        return self
