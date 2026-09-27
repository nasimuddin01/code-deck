"""`source = "jsonl"`: read an agent's own per-session log files.

Many CLI agents write one JSON-lines file per session (Codex and Claude Code
both do). Point CODE DECK at the files and name the fields:

    [agents.my-agent]
    source = "jsonl"
    files = "~/.my-agent/sessions/**/*.jsonl"   # glob; ** recurses
    session = "file"                  # session id: "file" (file name), "dir" (folder name) or a field path
    match = { type = "usage" }        # optional: only count lines whose fields equal these
    timestamp = "timestamp"           # ISO-8601 or epoch seconds/ms; default: the file's mtime
    model = "model"
    cwd = "cwd"
    tokens_in = "usage.input_tokens"  # dot paths; list items by index: "choices.0.usage"
    tokens_out = "usage.output_tokens"
    cost = "usage.cost_usd"
    totals = "sum"                    # "sum": each line is a delta (default) · "last": lines carry running totals
    waiting_when = { type = "approval_request" }   # optional: last line matches -> blue "needs you"
    done_when = { type = "turn_complete" }         # optional: last line matches -> "turn ended"

Only today's lines count (local time). A file written in the last two
minutes is a live session; one untouched for 20 minutes drops off the list.
Files are read incrementally, so large logs cost little after the first pass.
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from ..providers.stats import SessionInfo, ToolStats
from .payload import ACTIVE_WINDOW, LIVE_WINDOW
from .registry import SourceContext, register_source
from .spec import AgentSpec


def get_path(obj: Any, path: str) -> Any:
    """`a.b.0.c` into nested dicts/lists; None when any step is missing."""
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.lstrip("-").isdigit():
            i = int(part)
            cur = cur[i] if -len(cur) <= i < len(cur) else None
        else:
            return None
        if cur is None:
            return None
    return cur


def _matches(obj: Any, cond: dict | None) -> bool:
    return not cond or all(get_path(obj, k) == v for k, v in cond.items())


def parse_ts(v: Any) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v) / 1000.0 if v > 1e11 else float(v)   # epoch ms vs s
    try:
        return datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _today_start() -> float:
    d = datetime.date.today()
    return datetime.datetime(d.year, d.month, d.day).timestamp()


@dataclass
class _FileState:
    ino: int = 0
    offset: int = 0
    day: float = 0.0
    tin: float = 0.0
    tout: float = 0.0
    cost: float = 0.0
    model: str = ""
    cwd: str = ""
    session: str = ""
    state: str = ""             # "", "waiting" or "done" from the last line
    hours: list[float] = field(default_factory=lambda: [0.0] * 24)


class JsonlSource:
    def __init__(self, spec: AgentSpec, ctx: SourceContext) -> None:
        o = spec.options
        pattern = o.get("files")
        if not pattern or not isinstance(pattern, str):
            raise ValueError('jsonl source needs `files = "<glob>"`')
        self.spec = spec
        self.pattern = os.path.expanduser(pattern)
        self.session_key = str(o.get("session", "file"))
        self.match = o.get("match") if isinstance(o.get("match"), dict) else None
        self.fields = {k: o.get(k) for k in ("timestamp", "model", "cwd", "tokens_in", "tokens_out", "cost")}
        self.totals = str(o.get("totals", "sum"))
        if self.totals not in ("sum", "last"):
            raise ValueError('`totals` must be "sum" or "last"')
        self.waiting_when = o.get("waiting_when") if isinstance(o.get("waiting_when"), dict) else None
        self.done_when = o.get("done_when") if isinstance(o.get("done_when"), dict) else None
        self._files: dict[str, _FileState] = {}

    def _field(self, obj: dict, name: str) -> Any:
        path = self.fields.get(name)
        return get_path(obj, path) if path else None

    def _read(self, path: str, st: _FileState, today: float) -> None:
        try:
            info = os.stat(path)
        except OSError:
            return
        if info.st_ino != st.ino or info.st_size < st.offset or st.day != today:
            fresh = _FileState(ino=info.st_ino, day=today)
            st.__dict__.update(fresh.__dict__)
        if info.st_size == st.offset:
            return
        with open(path, "rb") as f:
            f.seek(st.offset)
            chunk = f.read()
        end = chunk.rfind(b"\n") + 1           # leave a half-written last line for next time
        st.offset += end
        for raw in chunk[:end].splitlines():
            try:
                obj = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(obj, dict):
                continue
            if self.waiting_when and _matches(obj, self.waiting_when):
                st.state = "waiting"
            elif self.done_when and _matches(obj, self.done_when):
                st.state = "done"
            elif self.waiting_when or self.done_when:
                st.state = ""
            if self.session_key not in ("file", "dir"):
                sid = get_path(obj, self.session_key)
                if sid:
                    st.session = str(sid)
            for name, attr in (("model", "model"), ("cwd", "cwd")):
                v = self._field(obj, name)
                if v:
                    setattr(st, attr, str(v))
            if not _matches(obj, self.match):
                continue
            ts = parse_ts(self._field(obj, "timestamp")) if self.fields.get("timestamp") else None
            if ts is not None and ts < today:
                continue
            tin, tout, cost = (_num(self._field(obj, k)) for k in ("tokens_in", "tokens_out", "cost"))
            before = st.tin + st.tout
            if self.totals == "sum":
                st.tin, st.tout, st.cost = st.tin + tin, st.tout + tout, st.cost + cost
            else:
                st.tin, st.tout, st.cost = max(st.tin, tin), max(st.tout, tout), max(st.cost, cost)
            hour = datetime.datetime.fromtimestamp(ts if ts is not None else time.time()).hour
            st.hours[hour] += st.tin + st.tout - before

    def stats(self) -> ToolStats:
        now = time.time()
        today = _today_start()
        paths = [p for p in glob.glob(self.pattern, recursive=True) if os.path.isfile(p)]
        seen = set()
        sessions: list[SessionInfo] = []
        tin = tout = cost = 0.0
        hours = [0.0] * 24
        model = ""
        for p in paths:
            try:
                mtime = os.path.getmtime(p)
            except OSError:
                continue
            if mtime < today:
                continue
            seen.add(p)
            st = self._files.setdefault(p, _FileState())
            self._read(p, st, today)
            tin, tout, cost = tin + st.tin, tout + st.tout, cost + st.cost
            hours = [a + b for a, b in zip(hours, st.hours, strict=True)]
            model = model or st.model
            if now - mtime > ACTIVE_WINDOW:
                continue
            base = os.path.basename(p).rsplit(".", 1)[0]
            sid = st.session or (os.path.basename(os.path.dirname(p)) if self.session_key == "dir" else base)
            label = os.path.basename(st.cwd.rstrip("/")) if st.cwd else sid
            live = now - mtime <= LIVE_WINDOW and not st.state
            sessions.append(SessionInfo(
                id=sid[:8] if len(sid) > 12 else sid, label=label, model=st.model, cwd=st.cwd,
                tokens_in=int(st.tin), tokens_out=int(st.tout), active=True, last_active=mtime,
                live=live, needs_input=bool(st.state),
                attention_kind="needs" if st.state == "waiting" else "idle" if st.state == "done" else ""))
        for gone in set(self._files) - seen:
            del self._files[gone]
        sessions.sort(key=lambda s: (s.live, s.needs_input, s.last_active), reverse=True)
        return ToolStats(name=self.spec.name, model=model, sessions_today=len(seen),
                         tokens_in=int(tin), tokens_out=int(tout), cost_usd=cost,
                         activity_24h=hours, live=True, active=any(s.live for s in sessions),
                         sessions=sessions)


register_source("jsonl", JsonlSource)
