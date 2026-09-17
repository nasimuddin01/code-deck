"""Authoritative Codex account data via a bundled app-server (stdio JSON-RPC).

The Codex desktop app ships an app-server binary that speaks newline-delimited
JSON-RPC over stdio and reads the shared ~/.codex state (auth, rate-limit cache).
We spawn ONE long-lived instance and pull:
  - account/rateLimits/read  -> weekly quota % (primary window), resets, plan
  - account/usage/read       -> per-day token buckets

This is fresher than tailing rollout files (which lag behind the live cache).
Everything is best-effort: any spawn/handshake/parse failure returns None and
the caller falls back to the rollout-file reader.

Not used: the desktop's private ~/.codex/ipc/ipc.sock — it is single-consumer
and closes external connections. A fresh stdio server is the supported path.
Framing is line-delimited JSON (NOT LSP Content-Length).
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import select
import subprocess
import threading
import time
from pathlib import Path

HOME = Path.home()
_BIN_CANDIDATES = [
    HOME / ".codex" / "plugins" / ".plugin-appserver" / "codex",
]


def _find_bin() -> str | None:
    for c in _BIN_CANDIDATES:
        if c.exists() and os.access(c, os.X_OK):
            return str(c)
    # fallback: any */codex under the plugin appserver dir
    for p in glob.glob(str(HOME / ".codex" / "plugins" / "*" / "codex")):
        if os.access(p, os.X_OK):
            return p
    return None


class CodexAppServer:
    """Persistent stdio app-server client. Thread-safe, respawns on failure."""

    CACHE_TTL = 60.0  # seconds; quota/usage change slowly, don't poll the backend every tick

    def __init__(self) -> None:
        self._bin = _find_bin()
        self._proc: subprocess.Popen | None = None
        self._buf = b""
        self._id = 1
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, object]] = {}

    def _cached(self, key: str, producer):
        hit = self._cache.get(key)
        if hit and (time.time() - hit[0]) < self.CACHE_TTL:
            return hit[1]
        val = producer()
        if val is not None:
            self._cache[key] = (time.time(), val)
        return val

    # -- process lifecycle --------------------------------------------------
    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _spawn(self) -> bool:
        if not self._bin:
            return False
        try:
            self._proc = subprocess.Popen(
                [self._bin, "app-server"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            self._proc = None
            return False
        self._buf = b""
        self._id = 1
        # initialize handshake
        resp = self._rpc("initialize", {
            "clientInfo": {"name": "code-deck", "title": None, "version": "0.1"},
            "capabilities": {"experimentalApi": False, "requestAttestation": False},
        }, timeout=6.0)
        if not resp or "result" not in resp:
            self._kill()
            return False
        self._notify("initialized")
        return True

    def _kill(self) -> None:
        if self._proc:
            try:
                self._proc.terminate()
            except OSError:
                pass
        self._proc = None
        self._buf = b""

    # -- wire ---------------------------------------------------------------
    def _write(self, obj: dict) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write((json.dumps(obj) + "\n").encode())
        self._proc.stdin.flush()

    def _notify(self, method: str, params: dict | None = None) -> None:
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)

    def _rpc(self, method: str, params: dict | None, timeout: float = 4.0) -> dict | None:
        """Send a request; read lines until the matching id response arrives.
        Notifications encountered in between are skipped."""
        rid = self._id
        self._id += 1
        msg = {"jsonrpc": "2.0", "method": method, "id": rid}
        if params is not None:
            msg["params"] = params
        try:
            self._write(msg)
        except (BrokenPipeError, OSError):
            return None
        end = time.time() + timeout
        fd = self._proc.stdout.fileno()  # type: ignore[union-attr]
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.3)
            if r:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    return None
                if not chunk:
                    return None
                self._buf += chunk
            while b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("id") == rid:
                    return obj
                # else: a notification or other response — ignore
        return None

    def _call(self, method: str, params: dict | None = None) -> dict | None:
        """Public entry: ensure alive, do one request, respawn once on failure."""
        with self._lock:
            for _attempt in (1, 2):
                if not self._alive() and not self._spawn():
                    return None
                resp = self._rpc(method, params)
                if resp and "result" in resp:
                    return resp["result"]
                # dead pipe / no response -> respawn and retry once
                self._kill()
            return None

    # -- high-level reads ---------------------------------------------------
    def rate_limits(self) -> dict | None:
        """Returns {'pct': float, 'resets_at': float|None, 'plan': str|None,
        'window_mins': int|None} for the primary (weekly) window, or None."""
        def produce():
            res = self._call("account/rateLimits/read")
            if not res:
                return None
            rl = res.get("rateLimits") or {}
            prim = rl.get("primary") or {}
            if prim.get("usedPercent") is None:
                return None
            resets = prim.get("resetsAt")
            return {
                "pct": float(prim["usedPercent"]),
                "resets_at": float(resets) if resets else None,
                "plan": rl.get("planType"),
                "window_mins": prim.get("windowDurationMins"),
            }
        return self._cached("rate_limits", produce)

    def usage_today(self) -> int | None:
        """Tokens recorded for today's date bucket, or None if not present."""
        def produce():
            res = self._call("account/usage/read")
            if not res:
                return None
            today = datetime.date.today().strftime("%Y-%m-%d")
            for b in res.get("dailyUsageBuckets") or []:
                if b.get("startDate") == today:
                    return int(b.get("tokens", 0) or 0)
            return None
        return self._cached("usage_today", produce)
