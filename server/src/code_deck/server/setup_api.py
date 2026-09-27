"""The GUI setup wizard's backend (the web app's /setup page).

GET  /api/setup/status            one entry per step, re-checked on every call
POST /api/setup/actions/<action>  do something about a step
GET  /api/setup/jobs/<id>         progress of a long action (installing Chromium...)

Actions run commands on this machine, so they are only accepted from this
machine (loopback) and never from another website (see `local_only`). Claude
Code's settings.json is still never written: the page shows the block, copies
it, and can open the file for the user.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from .. import __version__, config

router = APIRouter(prefix="/api/setup")

OK, WARN, ERROR, INFO = "ok", "warn", "error", "info"
DOCS = "https://github.com/ehfazrezwan/code-deck/blob/main/docs"


# -- safety ------------------------------------------------------------------------

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def local_only(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in LOCAL_HOSTS:
        raise HTTPException(403, "setup actions are only available on this computer")


# -- jobs (long actions) ------------------------------------------------------------

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _start_job(title: str, cmd: list[str], after=None) -> str:
    jid = uuid.uuid4().hex[:10]
    job = {"id": jid, "title": title, "status": "running", "log": "", "started": time.time()}
    with _jobs_lock:
        _jobs[jid] = job

    def run():
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            assert p.stdout is not None
            for line in p.stdout:
                with _jobs_lock:
                    job["log"] = (job["log"] + line)[-4000:]
            ok = p.wait() == 0
            if ok and after:
                after()
            job["status"] = "done" if ok else "failed"
        except Exception as e:  # command missing, etc.
            job["log"] += f"\n{e}"
            job["status"] = "failed"

    threading.Thread(target=run, name=f"setup-{jid}", daemon=True).start()
    return jid


# -- checks -------------------------------------------------------------------------

def _step(sid: str, title: str, status: str, detail: str, actions: list[dict] | None = None,
          **extra: Any) -> dict:
    return {"id": sid, "title": title, "status": status, "detail": detail,
            "actions": actions or [], **extra}


def _libusb() -> dict:
    from ..turzx import libusb
    path = libusb.find_libusb()
    if path:
        return _step("libusb", "USB driver (libusb)", OK, f"Found at {path}")
    acts = [{"id": "install-libusb", "label": "Install with Homebrew"}] if shutil.which("brew") else []
    return _step("libusb", "USB driver (libusb)", ERROR,
                 f"Not found. Install it ({libusb.INSTALL_HINT}) or set CODE_DECK_LIBUSB.", acts)


def _device(ctx) -> dict:
    dev = ctx.store.get("device")
    acts = [{"id": "test-pattern", "label": "Show test pattern"}] if ctx.device_loop else []
    if dev.get("connected"):
        return _step("device", "TURZX screen", OK,
                     "Connected and showing the dashboard. Show the test pattern to double-check.", acts)
    try:
        from ..turzx.usbraw import find_device
        present = find_device() is not None
    except Exception:
        present = False
    if present:
        return _step("device", "TURZX screen", WARN,
                     "Plugged in but not drawing yet. Close any app using the screen "
                     "(the vendor app, a serial monitor); it reconnects within a few seconds.", acts)
    return _step("device", "TURZX screen", WARN,
                 "Not found. Plug it in with a data-capable USB cable (many charge-only cables fit "
                 "but don't work). No restart needed: it's picked up automatically.")


def _chromium(ctx) -> dict:
    ok = ctx.store.get("device").get("chromium_ok")
    if ok:
        return _step("renderer", "Dashboard renderer", OK, "Headless Chromium is running.")
    installed = False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            installed = Path(p.chromium.executable_path).exists()
    except Exception:
        pass
    if installed:
        return _step("renderer", "Dashboard renderer", INFO,
                     "Installed. It starts with the service (restart it if the screen stays blank).",
                     [{"id": "restart-service", "label": "Restart service"}] if config.IS_MAC else [])
    return _step("renderer", "Dashboard renderer", ERROR,
                 "Headless Chromium draws the dashboard and needs a one-time download.",
                 [{"id": "install-chromium", "label": "Download it"}])


def _claude() -> dict:
    if not config.CLAUDE_DIR.exists():
        return _step("claude", "Claude Code", INFO,
                     f"Not found at {config.CLAUDE_DIR}. Skip this if you don't use Claude Code.")
    try:
        settings = json.loads(config.CLAUDE_SETTINGS.read_text())
    except (OSError, ValueError):
        settings = {}
    hook_cmd = config.hook_command()
    hooks = settings.get("hooks", {}) or {}
    missing_hooks = [ev for ev in config.HOOK_EVENTS
                     if not any("code-deck-hook" in h.get("command", "") or "code_deck.hooks" in h.get("command", "")
                                for m in hooks.get(ev) or [] if isinstance(m, dict)
                                for h in m.get("hooks") or [] if isinstance(h, dict))]
    env = settings.get("env", {}) or {}
    want_env = config.claude_telemetry_env()
    missing_env = {k: v for k, v in want_env.items() if env.get(k) != v}
    if not missing_hooks and not missing_env:
        return _step("claude", "Claude Code", OK, "Hooks and telemetry are set up.")
    block: dict = {}
    if missing_hooks:
        block["hooks"] = {ev: [{"hooks": [{"type": "command", "command": hook_cmd}]}] for ev in config.HOOK_EVENTS}
    if missing_env:
        block["env"] = want_env
    parts = [x for x, m in (("hooks (needs-you / turn-ended status)", missing_hooks),
                            ("telemetry (exact spend)", missing_env)) if m]
    acts = [{"id": "copy-claude", "label": "Copy block"}]
    if config.IS_MAC:
        acts.append({"id": "open-claude-settings", "label": "Open settings.json"})
    return _step("claude", "Claude Code", WARN,
                 f"Add {' and '.join(parts)}: merge this block into {config.CLAUDE_SETTINGS}, save, "
                 "then restart your Claude Code sessions. CODE DECK never edits that file itself.",
                 acts, snippet=json.dumps(block, indent=2))


def _codex() -> dict:
    if not config.CODEX_DIR.exists():
        return _step("codex", "Codex", INFO, "Not found. Optional.")
    if config.CODEX_APPSERVER_BIN.exists():
        return _step("codex", "Codex", OK, "Found, with live weekly quota from the Codex app-server.")
    return _step("codex", "Codex", OK, "Found. Quota is read from its session files.")


def _agents(ctx) -> dict:
    agents = ctx.store.get("agents") or []
    bad = [a for a in agents if a.get("error")]
    custom = [a["name"] for a in agents if not a.get("builtin")]
    detail = (f"{len(agents)} agents" + (f", including {', '.join(custom)}" if custom else " (the built-ins)")
              + f". Add others in {config.AGENTS_FILE}: {DOCS}/agents.md")
    if bad:
        detail = "; ".join(f"{a['id']}: {a['error']}" for a in bad)
    acts = [{"id": "open-config", "label": "Open config folder"}] if config.IS_MAC else []
    return _step("agents", "Coding agents", ERROR if bad else OK, detail, acts)


def _service() -> dict:
    if not config.IS_MAC:
        return _step("service", "Background service", INFO,
                     "Linux: run `code-deck serve` under systemd, or use Docker Compose.")
    from ..service import launchd
    st = launchd.status()
    if st.get("running"):
        return _step("service", "Background service", OK, "Starts at login and restarts if it crashes.")
    return _step("service", "Background service", WARN,
                 "Running for now, but not installed to start at login.",
                 [{"id": "install-service", "label": "Start at login"}])


def _telemetry_port() -> dict:
    with socket.socket() as s:
        s.settimeout(0.3)
        up = s.connect_ex(("127.0.0.1", config.OTLP_PORT)) == 0
    if up:
        return _step("telemetry", "Telemetry receiver", OK, f"Listening on port {config.OTLP_PORT}.")
    return _step("telemetry", "Telemetry receiver", WARN,
                 f"Port {config.OTLP_PORT} isn't answering; another program may hold it. "
                 f"Set CODE_DECK_OTLP_PORT in {config.USER_ENV_FILE} and restart.")


@router.get("/status")
def status(request: Request) -> dict:
    ctx = request.app.state.ctx
    steps = [_libusb(), _device(ctx), _chromium(ctx), _claude(), _codex(), _agents(ctx),
             _telemetry_port(), _service()]
    blocking = [s["id"] for s in steps if s["status"] == ERROR]
    return {"version": __version__, "platform": sys.platform, "steps": steps,
            "ready": not blocking, "done": setup_done(), "port": config.DEFAULT_PORT,
            "config_file": str(config.USER_ENV_FILE), "agents_file": str(config.AGENTS_FILE)}


# -- actions ------------------------------------------------------------------------

def _restart_service_soon() -> None:
    """Reinstall the launchd job a moment from now, so this response gets out
    before the process that is sending it is replaced."""
    from ..service import launchd

    def later():
        time.sleep(0.8)
        launchd.install()
    threading.Thread(target=later, daemon=True).start()


@router.post("/actions/{action}")
def action(request: Request, action: str) -> dict:
    local_only(request)
    ctx = request.app.state.ctx
    if action == "install-chromium":
        cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
        if sys.platform.startswith("linux"):
            cmd.append("--with-deps")
        after = _restart_service_soon if config.IS_MAC else None
        return {"job": _start_job("Downloading Chromium", cmd, after)}
    if action == "install-libusb":
        brew = shutil.which("brew")
        if not brew:
            raise HTTPException(400, "Homebrew isn't installed")
        return {"job": _start_job("Installing libusb", [brew, "install", "libusb"])}
    if action == "test-pattern":
        if not ctx.device_loop:
            raise HTTPException(400, "no device renderer running")
        ctx.device_loop.show_test(6)
        return {"ok": True, "message": "Look at the screen: 'CODE DECK' and three coloured bars for 6 seconds."}
    if action == "copy-claude":
        snippet = _claude().get("snippet", "")
        if not snippet:
            return {"ok": True, "message": "Nothing to copy: Claude Code is already set up."}
        if shutil.which("pbcopy"):
            subprocess.run(["pbcopy"], input=snippet.encode(), check=False)
            return {"ok": True, "message": "Copied. Paste it into settings.json."}
        return {"ok": True, "copy": snippet}
    if action == "open-claude-settings" and config.IS_MAC:
        path = config.CLAUDE_SETTINGS
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n")          # an empty object so the editor has a file to open
        subprocess.run(["open", "-t", str(path)], check=False)
        return {"ok": True}
    if action == "open-config" and config.IS_MAC:
        config.HOME.mkdir(parents=True, exist_ok=True)
        subprocess.run(["open", str(config.HOME)], check=False)
        return {"ok": True}
    if action in ("install-service", "restart-service") and config.IS_MAC:
        if config.is_dev_checkout() and action == "install-service":
            raise HTTPException(400, "running from a development checkout; install from your installed copy")
        _restart_service_soon()
        return {"ok": True, "message": "Restarting; this page reconnects in a few seconds."}
    if action == "finish":
        config.HOME.mkdir(parents=True, exist_ok=True)
        (config.HOME / ".setup-done").write_text(str(time.time()))
        return {"ok": True}
    raise HTTPException(404, f"unknown action {action!r}")


@router.get("/jobs/{jid}")
def job(jid: str) -> dict:
    with _jobs_lock:
        j = _jobs.get(jid)
        if not j:
            raise HTTPException(404, "no such job")
        return dict(j)


def setup_done() -> bool:
    return (config.HOME / ".setup-done").exists() or bool(os.environ.get("CODE_DECK_SKIP_SETUP"))
