"""Live (poll-based) stats providers for Claude Code + Codex.

Zero-setup: reads only local on-disk state, no OTEL / hooks / daemon required.
This is the "poll now" stage of the staged plan; push transports (Claude Code
OTEL, Codex app-server JSON-RPC) can later replace the internals of each
provider behind the same get_stats() -> list[ToolStats] interface.

Sources:
  Claude Code  ~/.claude/projects/<proj>/<session>.jsonl   (assistant lines: model + usage)
  Codex        ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl (token_count + rate_limits)
               ~/.codex/thread-writer-locks/<thread>.lock   (flock -> live sessions via lsof)
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import subprocess
import time
from pathlib import Path

from .codex_appserver import CodexAppServer
from .otel_receiver import OtelReceiver
from .stats import SessionInfo, ToolStats

HOME = Path.home()
CLAUDE_PROJECTS = HOME / ".claude" / "projects"
CODEX_SESSIONS = HOME / ".codex" / "sessions"
CODEX_LOCKS = HOME / ".codex" / "thread-writer-locks"
ATTENTION_DIR = HOME / ".claude" / "code-deck" / "attention"

ACTIVE_WINDOW = 20 * 60    # seconds; only sessions written this recently appear in the list
LIVE_WINDOW = 120          # seconds; written this recently => agent working NOW (green dot)
ATTENTION_TTL = 60 * 60    # seconds; ignore attention flags older than this (stale)
MAX_INITIAL_PARSE = 60 * 1024 * 1024  # skip pathologically huge files on first read


def _attention_sessions() -> dict[str, tuple[float, str]]:
    """Map session_id -> (flag mtime, kind) for fresh Notification-hook flags.

    Comparing the flag time against the transcript mtime lets the caller show
    the blue dot only while the notification is the most recent event (the
    session is waiting); once the agent writes again, the flag goes stale.
    `kind` is "needs" (blocked on you) or "idle" (turn ended); defaults to
    "needs" if the flag can't be read.
    """
    now = time.time()
    out: dict[str, tuple[float, str]] = {}
    for p in glob.glob(str(ATTENTION_DIR / "*.json")):
        try:
            mt = os.path.getmtime(p)
        except OSError:
            continue
        if now - mt > ATTENTION_TTL:
            continue
        kind = "needs"
        try:
            with open(p) as f:
                kind = json.load(f).get("kind", "needs") or "needs"
        except (OSError, ValueError):
            pass
        out[Path(p).stem] = (mt, kind)
    return out


def _today_start() -> float:
    now = datetime.datetime.now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def _parse_ts(s: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()
    except (ValueError, AttributeError):
        return None


def _short_label(project_dir: str) -> str:
    # "-Users-alice-Projects-code-display" -> "code-display"
    parts = project_dir.rstrip("-").split("-")
    return parts[-1] if parts else project_dir


# --- Claude Code cost estimate (per-token USD), by model family ------------------
# Real dollars come later from OTEL (claude_code.cost.usage). Fable has no public
# price yet; treated as an estimate and flagged cost_estimated=True.
_CC_PRICES = {  # (input, output, cache_write, cache_read)
    "opus":   (15 / 1e6, 75 / 1e6, 18.75 / 1e6, 1.5 / 1e6),
    "sonnet": (3 / 1e6, 15 / 1e6, 3.75 / 1e6, 0.3 / 1e6),
    "haiku":  (1 / 1e6, 5 / 1e6, 1.25 / 1e6, 0.1 / 1e6),
    "fable":  (5 / 1e6, 25 / 1e6, 6.25 / 1e6, 0.5 / 1e6),  # estimate
}


def _cc_family(model: str) -> str:
    m = (model or "").lower()
    for k in ("opus", "sonnet", "haiku", "fable"):
        if k in m:
            return k
    return "sonnet"


def _read_appended(path: str, offset: int) -> tuple[bytes, int]:
    """Read whole lines appended since `offset`; return (data, new_offset).

    Only consumes up to the last newline so a half-written trailing line is
    left for the next poll.
    """
    with open(path, "rb") as f:
        f.seek(offset)
        chunk = f.read()
    nl = chunk.rfind(b"\n")
    if nl == -1:
        return b"", offset
    return chunk[:nl + 1], offset + nl + 1


class ClaudeCodeLiveProvider:
    """Aggregates today's Claude Code usage across all session transcripts.

    Cost is a token-price ESTIMATE by default. When an OtelReceiver is wired in
    and Claude Code telemetry is enabled, a session's authoritative Vertex $
    (claude_code.cost.usage, keyed by session.id == transcript UUID) replaces
    the estimate for that session; the card is flagged estimated only if some
    session still lacks an OTEL reading.
    """

    def __init__(self, otel=None) -> None:
        # path -> dict(ino, offset, day, tin, tout, cost, model, hours[24])
        self._state: dict[str, dict] = {}
        self._cwd_cache: dict[str, str] = {}
        self.otel = otel

    def _files(self) -> list[str]:
        return [p for p in glob.glob(str(CLAUDE_PROJECTS / "*" / "*.jsonl"))
                if os.sep + "subagents" + os.sep not in p]

    def _label_for(self, path: str) -> str:
        """Working-directory basename from the transcript's `cwd` field; falls
        back to the (lossy) encoded project-dir name if none is present."""
        cwd = self._cwd_for(path)
        return (os.path.basename(cwd.rstrip("/")) if cwd else "") or _short_label(Path(path).parent.name)

    def _cwd_for(self, path: str) -> str:
        """Full working directory from the transcript's `cwd` field ("" if none)."""
        if path not in self._cwd_cache:
            cwd = ""
            try:
                with open(path, "rb") as f:
                    head = f.read(64 * 1024).decode("utf-8", "replace")
                for ln in head.splitlines():
                    if '"cwd"' in ln:
                        try:
                            cwd = json.loads(ln).get("cwd", "") or ""
                        except ValueError:
                            cwd = ""
                        if cwd:
                            break
            except OSError:
                pass
            self._cwd_cache[path] = cwd
        return self._cwd_cache[path]

    def _update_file(self, path: str, today: str) -> dict:
        try:
            stt = os.stat(path)
        except OSError:
            return {}
        s = self._state.get(path)
        fresh = (
            s is None or s["ino"] != stt.st_ino
            or s["day"] != today or stt.st_size < s["offset"]
        )
        if fresh:
            start = 0
            if stt.st_size > MAX_INITIAL_PARSE:
                start = stt.st_size  # too big to backfill; tail forward only
            s = {"ino": stt.st_ino, "offset": start, "day": today, "convo": False,
                 "tin": 0, "tout": 0, "cost": 0.0, "model": "", "hours": [0.0] * 24}
            self._state[path] = s
        if stt.st_size <= s["offset"]:
            return s
        data, new_off = _read_appended(path, s["offset"])
        s["offset"] = new_off
        for raw in data.splitlines():
            # real conversation vs. bookkeeping file: a Claude Code restart can
            # leave a session file holding only state records (last-prompt,
            # cost-state, file-history-snapshot) — no user/assistant lines
            if not s["convo"] and (b'"user"' in raw or b'"assistant"' in raw):
                try:
                    if json.loads(raw).get("type") in ("user", "assistant"):
                        s["convo"] = True
                except ValueError:
                    pass
            if b'"assistant"' not in raw:
                continue
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            if rec.get("type") != "assistant":
                continue
            dt = _parse_ts(rec.get("timestamp", ""))
            if dt is None or dt.strftime("%Y-%m-%d") != today:
                continue
            msg = rec.get("message", {}) or {}
            u = msg.get("usage", {}) or {}
            if not u:
                continue
            model = msg.get("model", "") or s["model"]
            it = int(u.get("input_tokens", 0) or 0)
            ot = int(u.get("output_tokens", 0) or 0)
            ccreat = int(u.get("cache_creation_input_tokens", 0) or 0)
            cread = int(u.get("cache_read_input_tokens", 0) or 0)
            pin, pout, pcw, pcr = _CC_PRICES[_cc_family(model)]
            s["cost"] += it * pin + ot * pout + ccreat * pcw + cread * pcr
            s["tin"] += it + ccreat + cread
            s["tout"] += ot
            s["hours"][dt.hour] += ot
            s["model"] = model
        return s

    def stats(self) -> ToolStats:
        today = datetime.date.today().strftime("%Y-%m-%d")
        today0 = _today_start()
        now = time.time()
        tin = tout = 0
        cost = 0.0
        hours = [0.0] * 24
        sessions: list[SessionInfo] = []
        newest_model, newest_mtime = "", 0.0
        active = False
        any_estimated = False
        today_count = 0
        attention = _attention_sessions()
        for path in self._files():
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if mtime < today0:
                self._state.pop(path, None)
                continue
            s = self._update_file(path, today)
            if not s:
                continue
            tin += s["tin"]
            tout += s["tout"]
            # authoritative Vertex $ from OTEL when this session reported it —
            # but OTEL only counts from when the session began exporting, so a
            # session that ran hours before telemetry (or before the receiver)
            # would undercount; take whichever covers more of the day
            otel_cost = self.otel.cost_for(Path(path).stem) if self.otel else None
            if otel_cost is not None and otel_cost >= s["cost"]:
                cost += otel_cost
            else:
                cost += s["cost"]
                if s["tin"] + s["tout"] > 0:
                    any_estimated = True
            for i in range(24):
                hours[i] += s["hours"][i]
            if s["tin"] + s["tout"] > 0:
                today_count += 1
            # list only recent sessions; anything older than the window drops off
            if (now - mtime) > ACTIVE_WINDOW:
                continue
            is_live = (now - mtime) <= LIVE_WINDOW
            if not is_live and s["tin"] + s["tout"] == 0:
                continue  # opened but no work yet and not writing now
            if not s.get("convo"):
                continue  # bookkeeping-only file (restart ghost), not a session
            active = True
            if mtime > newest_mtime:
                newest_mtime, newest_model = mtime, s["model"]
            full_id = Path(path).stem
            # blue "needs you" while the notification is the most recent event;
            # once the agent writes again (mtime advances) the flag goes stale
            flag = attention.get(full_id)
            needs_input = flag is not None and flag[0] >= mtime - 5
            attn_kind = flag[1] if (flag and needs_input) else ""
            sessions.append(SessionInfo(
                id=full_id[:8], label=self._label_for(path), model=s["model"],
                cwd=self._cwd_for(path),
                tokens_in=s["tin"], tokens_out=s["tout"],
                active=True, last_active=mtime,
                live=is_live, needs_input=needs_input, attention_kind=attn_kind,
            ))
        sessions.sort(key=lambda x: (x.active, x.last_active), reverse=True)
        return ToolStats(
            name="Claude Code",
            model=(newest_model or "-").replace("claude-", ""),
            sessions_today=today_count,
            tokens_in=tin, tokens_out=tout, cost_usd=cost,
            activity_24h=hours, live=True, active=active,
            cost_estimated=any_estimated, sessions=sessions,
        )


def _tail_text(path: str, n: int = 512 * 1024) -> list[str]:
    """Last ~n bytes of a file as complete lines (drops a partial first line)."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, size - n))
            chunk = f.read()
    except OSError:
        return []
    if size > n:
        nl = chunk.find(b"\n")
        chunk = chunk[nl + 1:] if nl != -1 else chunk
    return chunk.decode("utf-8", "replace").splitlines()


class CodexLiveProvider:
    """Reads the most-recent Codex rollout for tokens + weekly quota + model."""

    def __init__(self) -> None:
        self._model_cache: dict[str, str] = {}
        self.appsrv = CodexAppServer()

    def _rollouts(self) -> list[str]:
        return sorted(
            glob.glob(str(CODEX_SESSIONS / "*" / "*" / "*" / "rollout-*.jsonl")),
            key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0,
            reverse=True,
        )

    def _live_threads(self) -> set[str]:
        locks = glob.glob(str(CODEX_LOCKS / "*.lock"))
        if not locks:
            return set()
        try:
            out = subprocess.run(["lsof", "--", *locks], capture_output=True,
                                 text=True, timeout=3).stdout
        except (OSError, subprocess.SubprocessError):
            return set()
        live = set()
        for line in out.splitlines()[1:]:
            name = line.split()[-1] if line.split() else ""
            if name.endswith(".lock"):
                live.add(Path(name).stem)
        return live

    def _model_for(self, path: str) -> str:
        if path in self._model_cache:
            return self._model_cache[path]
        model = ""
        # thread_settings_applied / turn_context sit near the file head
        try:
            with open(path, "rb") as f:
                head = f.read(256 * 1024).decode("utf-8", "replace")
            for ln in reversed(head.splitlines()):
                if '"model"' in ln:
                    try:
                        rec = json.loads(ln)
                    except ValueError:
                        continue
                    ts = (rec.get("payload", {}) or {}).get("thread_settings", {}) or {}
                    model = ts.get("model") or rec.get("payload", {}).get("model") or ""
                    if model:
                        break
        except OSError:
            pass
        if model:
            self._model_cache[path] = model
        return model

    def _latest_quota(self, rollouts: list[str]) -> tuple[float | None, float | None]:
        """Weekly quota is account-wide; take the freshest non-null reading
        across the most recent rollouts (the newest session may be idle)."""
        for path in rollouts[:6]:
            for ln in reversed(_tail_text(path)):
                if '"rate_limits"' not in ln:
                    continue
                try:
                    rl = (json.loads(ln).get("payload", {}) or {}).get("rate_limits")
                except ValueError:
                    continue
                prim = (rl or {}).get("primary") or {}
                if prim.get("used_percent") is not None:
                    reset = prim.get("resets_at")
                    return float(prim["used_percent"]), float(reset) if reset else None
        return None, None

    def stats(self) -> ToolStats:
        rollouts = self._rollouts()
        today0 = _today_start()
        now = time.time()
        live_threads = self._live_threads()
        today_count = sum(1 for p in rollouts if os.path.getmtime(p) >= today0)
        sessions_today = max(today_count, len(live_threads))

        if not rollouts:
            return ToolStats(name="Codex", model="-", sessions_today=0,
                             tokens_in=0, tokens_out=0, cost_usd=0.0,
                             activity_24h=[0.0] * 24, live=True)

        newest = rollouts[0]
        thread_id = newest.split("rollout-")[-1].rsplit(".jsonl", 1)[0]
        thread_id = thread_id.split("-", 3)[-1] if thread_id.count("-") >= 5 else thread_id
        # "active" = written within the window (a held lock alone can be an idle
        # session held open for hours), matching the Claude Code semantics.
        newest_mtime = os.path.getmtime(newest)
        active = (now - newest_mtime) <= ACTIVE_WINDOW
        is_live = (now - newest_mtime) <= LIVE_WINDOW

        tin = tout = 0
        for ln in reversed(_tail_text(newest)):
            if '"token_count"' not in ln:
                continue
            try:
                rec = json.loads(ln)
            except ValueError:
                continue
            payload = rec.get("payload", {}) or {}
            if payload.get("type") != "token_count":
                continue
            tot = (payload.get("info", {}) or {}).get("total_token_usage", {}) or {}
            tin = int(tot.get("input_tokens", 0) or 0) + int(tot.get("cached_input_tokens", 0) or 0)
            tout = int(tot.get("output_tokens", 0) or 0) + int(tot.get("reasoning_output_tokens", 0) or 0)
            if tin == 0 and tout == 0:
                tout = int(tot.get("total_tokens", 0) or 0)
            break

        # authoritative account quota from the app-server; rollout tail fallback
        rl = None
        try:
            rl = self.appsrv.rate_limits()
        except Exception:
            rl = None
        if rl:
            quota_pct, quota_reset = rl["pct"], rl["resets_at"]
        else:
            quota_pct, quota_reset = self._latest_quota(rollouts)

        # only list the Codex thread if it's recent (same window as Claude Code)
        codex_sessions = []
        if active:
            codex_sessions.append(SessionInfo(
                id=thread_id[:8], label="codex",
                tokens_in=tin, tokens_out=tout, active=True,
                last_active=newest_mtime, live=is_live))

        return ToolStats(
            name="Codex",
            model=self._model_for(newest) or "-",
            sessions_today=sessions_today,
            tokens_in=tin, tokens_out=tout, cost_usd=0.0,
            activity_24h=[0.0] * 24, live=True, active=active,
            quota_pct=quota_pct,
            quota_resets_at=float(quota_reset) if quota_reset else None,
            sessions=codex_sessions,
        )


class ClaudeMaxProvider:
    """Claude Max subscription quota (account-level, separate from the Vertex
    API billing that ClaudeCodeLiveProvider costs out).

    When Claude Code is billed through an API provider (e.g. Vertex), the Max plan is
    currently *paused* and exposes no local quota file. This provider is the
    seam for that card: _read_quota() returns None while paused (card shows
    "paused"), and lights up automatically once a real reading is available.

    Phase 2 wires the real source (Claude Code OTEL rate-limit metrics, the
    statusline /status rate_limits payload, or a lightweight authenticated
    header probe) into _read_quota().
    """

    def _read_quota(self) -> tuple[float | None, float | None]:
        # No live Max quota source while the subscription is paused.
        return None, None

    def stats(self) -> ToolStats:
        pct, reset = self._read_quota()
        note = "" if pct is not None else "paused"
        return ToolStats(
            name="Claude Max",
            model="subscription",
            sessions_today=0,
            tokens_in=0, tokens_out=0, cost_usd=0.0,
            activity_24h=[0.0] * 24, live=True, active=False,
            quota_pct=pct,
            quota_resets_at=reset,
            note=note,
        )


class LiveStatsProvider:
    """Composite: Claude Code (Vertex $) + Claude Max (quota) + Codex (quota).

    Owns the in-process OTLP receiver so Claude Code sessions that export
    telemetry (~/.claude/settings.json env) report authoritative $ here. The
    receiver is best-effort: if the port is taken or binding fails, the Claude
    Code card silently falls back to the token-price estimate.
    """

    def __init__(self) -> None:
        self.otel = None
        try:
            self.otel = OtelReceiver().start()
        except OSError:
            self.otel = None
        self.cc = ClaudeCodeLiveProvider(otel=self.otel)
        self.cmax = ClaudeMaxProvider()
        self.codex = CodexLiveProvider()

    def get_stats(self) -> list[ToolStats]:
        return [self.cc.stats(), self.cmax.stats(), self.codex.stats()]
