"""`code-deck` command line."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path

import typer

from . import __version__, config

app = typer.Typer(help="CODE DECK — Claude Code + Codex dashboard on a TURZX USB screen.",
                  no_args_is_help=True, add_completion=False)
service_app = typer.Typer(help="Manage the background service (macOS launchd).",
                          no_args_is_help=True)
hooks_app = typer.Typer(help="Claude Code hook integration.", no_args_is_help=True)
agents_app = typer.Typer(help="Your coding agents: built-ins plus agents.toml (docs/agents.md).",
                         no_args_is_help=True)
env_app = typer.Typer(help="CODE DECK .env template and Claude Code telemetry env.", no_args_is_help=True)
app.add_typer(service_app, name="service")
app.add_typer(hooks_app, name="hooks")
app.add_typer(env_app, name="env")
app.add_typer(agents_app, name="agents")

OK, BAD, WARN, INFO = "✓", "✗", "!", "·"


_hook_command = config.hook_command


def _read_settings() -> dict | None:
    try:
        with open(config.CLAUDE_SETTINGS) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# -- serve ------------------------------------------------------------------

@app.command()
def serve(
    renderer: str = typer.Option(config.DEFAULT_RENDERER, help="chromium | pil (legacy) | none (API only)"),
    host: str = typer.Option(config.DEFAULT_HOST, help="0.0.0.0 to expose the builder on the LAN"),
    port: int = typer.Option(config.DEFAULT_PORT),
    interval: float | None = typer.Option(None, help="seconds between polls (default: layout setting)"),
    brightness: int | None = typer.Option(None, min=0, max=255,
                                          help="raw panel brightness (default: layout setting)"),
    overlay: bool | None = typer.Option(None, help="full-screen banner when a session needs you"),
    overlay_seconds: float | None = typer.Option(None),
    no_device: bool = typer.Option(False, help="render to the preview file only"),
    mock: bool = typer.Option(False, help="dummy data instead of Claude/Codex files"),
    player_url: str | None = typer.Option(config.PLAYER_URL or None, help="render this URL instead of the bundled player "
                                                     "(e.g. the Vite dev server)"),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
) -> None:
    """Run the server + dashboard (foreground). `service install` runs this for you."""
    import uvicorn

    from .log import setup
    from .runtime import Runtime
    setup(verbose)
    try:
        rt = Runtime(renderer=renderer, host=host, port=port, interval=interval,
                     brightness=brightness, overlay=overlay, overlay_seconds=overlay_seconds,
                     no_device=no_device, mock=mock, player_url=player_url)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(2) from None
    rt.start()
    typer.echo(f"CODE DECK on http://{host}:{port}  (renderer={renderer})", err=True)
    try:
        uvicorn.run(rt.app, host=host, port=port, log_config=None, access_log=False)
    finally:
        rt.shutdown()


@app.command()
def init(
    yes: bool = typer.Option(False, "--yes", "-y", help="accept every default, no prompts"),
    env_file: Path | None = typer.Option(None, help=f"where to save settings (default {config.USER_ENV_FILE})"),
) -> None:
    """First-run setup wizard: libusb, the screen, renderer, ports, Claude Code, service."""
    from . import wizard
    wizard.run(yes=yes, env_file=env_file)


@app.command()
def setup() -> None:
    """One-time: install the headless Chromium the renderer uses."""
    import subprocess

    from .turzx import libusb
    cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
    if sys.platform.startswith("linux"):
        cmd.append("--with-deps")
    typer.echo(f"{INFO} {' '.join(cmd)}")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise typer.Exit(r.returncode)
    typer.echo(f"{OK} chromium installed")
    path = libusb.find_libusb()
    typer.echo(f"{OK if path else BAD} libusb: {path or f'not found ({libusb.INSTALL_HINT})'}")


@app.command()
def render(
    out: Path = typer.Argument(Path("frame.png"), help="PNG to write"),
    mock: bool = typer.Option(False, help="dummy data (deterministic-ish, no Claude/Codex files)"),
    player_url: str | None = typer.Option(None),
    timeout: float = typer.Option(30.0),
    overlay: bool = typer.Option(False, help="let the needs-you banner play (off: a stable frame)"),
) -> None:
    """Render one frame with the Chromium renderer, no device needed (CI golden)."""
    from .log import setup as log_setup
    from .render.chromium import ChromiumRenderer
    from .runtime import Runtime, free_port
    log_setup(False)
    port = free_port()
    try:
        rt = Runtime(renderer="none", port=port, mock=mock, overlay=overlay)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(2) from None
    rt.start()
    server = rt.serve_in_thread()
    r = ChromiumRenderer(player_url or f"http://127.0.0.1:{port}/player?device=1")
    try:
        r.start()
        deadline = time.time() + timeout
        frame = None
        while frame is None and time.time() < deadline:
            frame = r.poll(timeout=1.0)
        if frame is None:
            typer.echo("no frame produced", err=True)
            raise typer.Exit(1)
        frame.save(out)
        typer.echo(f"{OK} wrote {out} ({frame.width}x{frame.height})")
    finally:
        r.stop()
        server.should_exit = True
        rt.shutdown()


# -- service ----------------------------------------------------------------

@service_app.command("install")
def service_install(
    port: int = typer.Option(config.DEFAULT_PORT),
    host: str = typer.Option(config.DEFAULT_HOST),
) -> None:
    """Install + start the launchd agent (starts at login, restarts on crash).
    Brightness/overlay come from the layout settings so the builder can change
    them without reinstalling."""
    from .service import launchd
    path = launchd.install(["--host", host, "--port", str(port)])
    typer.echo(f"{OK} installed {path}")
    typer.echo(f"{OK} started {config.LAUNCHD_LABEL}; logs in {config.LOG_DIR}")


@service_app.command("uninstall")
def service_uninstall() -> None:
    from .service import launchd
    removed = launchd.uninstall()
    typer.echo(f"{OK} stopped and removed" if removed else f"{INFO} nothing installed")


@service_app.command("restart")
def service_restart() -> None:
    from .service import launchd
    launchd.restart()
    typer.echo(f"{OK} restarted {config.LAUNCHD_LABEL}")


@service_app.command("status")
def service_status() -> None:
    from .service import launchd
    st = launchd.status()
    for k, v in st.items():
        typer.echo(f"{k:10} {v}")
    raise typer.Exit(0 if st["running"] else 1)


@service_app.command("logs")
def service_logs(lines: int = typer.Option(50, "-n")) -> None:
    from .service import launchd
    for p in launchd.log_files():
        if p.exists():
            typer.echo(f"── {p} ──")
            typer.echo("".join(p.read_text(errors="replace").splitlines(True)[-lines:]))


# -- hooks / env (printed for the user to paste; never written) --------------

@hooks_app.command("print")
def hooks_print() -> None:
    """Print the `hooks` block to merge into ~/.claude/settings.json."""
    entry = [{"hooks": [{"type": "command", "command": _hook_command()}]}]
    typer.echo(json.dumps({"hooks": dict.fromkeys(config.HOOK_EVENTS, entry)}, indent=2))


EXAMPLE_HEADER = """# CODE DECK configuration. Copy to `.env` (repo checkout / Docker) or to
# ~/.config/code-deck/.env (installed service + menu bar app), or run
# `code-deck init`, which writes the latter for you.
#
# Every line is optional: the commented values are the defaults. Only
# CODE_DECK_* keys are read, and the real environment always wins over this
# file. Nothing secret belongs here. Claude Code's own telemetry variables go
# in ~/.claude/settings.json instead (`code-deck env print`).
#
# Generated by `code-deck env example`; edit config.ENV_SPEC, not this file."""


@env_app.command("example")
def env_example() -> None:
    """Print a fully commented .env template (the repo's .env.example)."""
    typer.echo(config.render_env_file(header=EXAMPLE_HEADER), nl=False)


@env_app.command("print")
def env_print() -> None:
    """Print the `env` block that makes Claude Code export cost telemetry to us."""
    typer.echo(json.dumps({"env": config.TELEMETRY_ENV}, indent=2))


# -- agents -------------------------------------------------------------------

def _server_get(path: str, timeout: float = 1.5):
    import urllib.request
    with urllib.request.urlopen(f"http://127.0.0.1:{config.DEFAULT_PORT}{path}", timeout=timeout) as r:
        return json.loads(r.read())


@agents_app.command("list")
def agents_list() -> None:
    """Show every agent and where its data comes from."""
    try:
        agents = _server_get("/api/agents")
        if not isinstance(agents, list):
            raise ValueError("unexpected response")
        where = "running server"
    except (OSError, ValueError):   # not running, or an older server without /api/agents
        from .agents import load_specs
        specs, errors = load_specs()
        agents = [{**s.public(), "error": ""} for s in specs]
        where = f"{config.AGENTS_FILE} (server not reachable, or an older version)"
        for e in errors:
            typer.echo(f"{BAD} {e}")
    typer.echo(f"{INFO} from {where}")
    for a in agents:
        mark = BAD if a.get("error") else (OK if a["enabled"] else INFO)
        tags = ", ".join(t for t, on in (("built-in", a.get("builtin")), ("pushed", a.get("dynamic")),
                                          ("disabled", not a["enabled"])) if on)
        typer.echo(f"{mark} {a['id']:<16} {a['name']:<18} {a['source']:<12} {a['color']:<9} {tags}"
                   + (f"  — {a['error']}" if a.get("error") else ""))


@app.command()
def push(
    agent: str = typer.Argument(..., help="agent id, e.g. my-agent (created on first push)"),
    session: str | None = typer.Argument(None, help="session id; omit to update agent-level totals"),
    state: str | None = typer.Option(None, help="working | waiting | done | idle"),
    label: str | None = typer.Option(None, help="row name (default: the cwd's folder name)"),
    cwd: str | None = typer.Option(None, help="project folder (default: current directory)"),
    model: str | None = typer.Option(None),
    tokens_in: int | None = typer.Option(None),
    tokens_out: int | None = typer.Option(None),
    cost: float | None = typer.Option(None, help="USD so far (session) or today (agent)"),
    quota: float | None = typer.Option(None, help="agent-level quota used, 0-100"),
    resets_at: float | None = typer.Option(None, help="agent-level quota reset, epoch seconds"),
    note: str | None = typer.Option(None, help="agent-level short status text"),
    end: bool = typer.Option(False, "--end", help="the session finished: remove it"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="never fail (for hooks): no output, exit 0"),
) -> None:
    """Report an agent's status to the running dashboard (for scripts and hooks).

    \b
    code-deck push my-agent "$SESSION_ID" --state working
    code-deck push my-agent "$SESSION_ID" --state waiting      # blue "needs you" + banner
    code-deck push my-agent "$SESSION_ID" --end
    code-deck push my-agent --cost 3.20 --quota 41
    """
    import os
    import urllib.error
    import urllib.request

    base = f"http://127.0.0.1:{config.DEFAULT_PORT}/api/agents/{agent}"
    if session is None:
        body = {"cost_usd": cost, "quota_pct": quota, "quota_resets_at": resets_at, "note": note,
                "model": model, "tokens_in": tokens_in, "tokens_out": tokens_out}
        url, method = base, "POST"
    else:
        path = cwd or os.getcwd()
        body = {"state": state, "label": label, "cwd": path, "model": model,
                "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": cost}
        url = f"{base}/sessions/{urllib.request.quote(session, safe='')}"
        method = "DELETE" if end else "POST"
    data = json.dumps({k: v for k, v in body.items() if v is not None}).encode()
    req = urllib.request.Request(url, data=None if method == "DELETE" else data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            r.read()
    except urllib.error.HTTPError as e:
        if not quiet:
            typer.echo(f"{BAD} {e.code}: {e.read().decode(errors='replace')}", err=True)
            raise typer.Exit(1) from None
        return
    except OSError as e:
        if not quiet:
            typer.echo(f"{BAD} dashboard not reachable on port {config.DEFAULT_PORT}: {e}", err=True)
            raise typer.Exit(1) from None
        return
    if not quiet:
        typer.echo(f"{OK} {agent}" + (f"/{session}" if session else "") + (" ended" if end else ""))


# -- doctor -----------------------------------------------------------------

@app.command()
def doctor() -> None:
    """Check libusb, the device, hooks, telemetry and the service."""
    from .turzx import libusb
    problems = 0

    def line(mark: str, msg: str) -> None:
        nonlocal problems
        if mark == BAD:
            problems += 1
        typer.echo(f"{mark} {msg}")

    line(INFO, f"code-deck {__version__} · python {sys.version.split()[0]} · {sys.executable}")
    line(INFO, f"home {config.HOME} · logs {config.LOG_DIR}")
    envs = ", ".join(str(p) for p in config.LOADED_ENV_FILES) or "none (defaults; `code-deck init` writes one)"
    line(INFO, f".env: {envs}")

    path = libusb.find_libusb()
    if path:
        line(OK, f"libusb: {path}")
        try:
            from .turzx.usbraw import PID, VID, find_device
            dev = find_device()
            line(OK if dev is not None else WARN,
                 f"TURZX device {VID:04x}:{PID:04x} " + ("present" if dev is not None else "not plugged in"))
        except Exception as e:
            line(BAD, f"libusb load failed: {e}")
    else:
        line(BAD, f"libusb not found ({libusb.INSTALL_HINT}, or set {libusb.ENV_VAR})")

    settings = _read_settings()
    if settings is None:
        line(WARN, f"{config.CLAUDE_SETTINGS} not readable — hooks/telemetry unchecked")
    else:
        hooks = settings.get("hooks", {}) or {}
        want = _hook_command()
        for ev in config.HOOK_EVENTS:
            cmds = [h.get("command", "") for m in (hooks.get(ev) or []) if isinstance(m, dict)
                    for h in (m.get("hooks") or []) if isinstance(h, dict)]
            if any(want in c or "code-deck-hook" in c for c in cmds):
                line(OK, f"hook {ev}: registered")
            elif any("attention_hook.py" in c for c in cmds):
                line(WARN, f"hook {ev}: points at the old dashboard/attention_hook.py — "
                           f"run `code-deck hooks print` and update")
            else:
                line(WARN, f"hook {ev}: not registered (`code-deck hooks print`)")
        env = settings.get("env", {}) or {}
        missing = [k for k, v in config.TELEMETRY_ENV.items() if env.get(k) != v]
        if not missing:
            line(OK, "telemetry env: all keys present")
        else:
            line(WARN, f"telemetry env missing or different: {', '.join(missing)} (`code-deck env print`)")

    with socket.socket() as s:
        s.settimeout(0.3)
        bound = s.connect_ex(("127.0.0.1", config.OTLP_PORT)) == 0
    line(OK if bound else INFO,
         f"OTLP receiver port {config.OTLP_PORT}: " + ("listening" if bound else "not listening (starts with serve)"))

    from .agents import load_specs
    specs, agent_errors = load_specs()
    custom = [s.id for s in specs if not s.builtin]
    for e in agent_errors:
        line(BAD, f"agents.toml: {e}")
    line(INFO, f"agents: {len(specs)} ({', '.join(custom) or 'built-ins only'}) · {config.AGENTS_FILE}")

    line(OK if config.CODEX_APPSERVER_BIN.exists() else INFO,
         "codex app-server: " + ("found" if config.CODEX_APPSERVER_BIN.exists()
                                  else "not found (Codex quota falls back to session files)"))

    if config.IS_MAC:
        from .service import launchd
        st = launchd.status()
        if st["running"]:
            line(OK, f"service: running (pid {st['pid']})")
        elif st["installed"]:
            line(WARN, "service: installed but not running (`code-deck service logs`)")
        else:
            line(INFO, "service: not installed (`code-deck service install`)")

    from .server.app import static_dir
    line(OK if static_dir() else WARN,
         "web app: " + ("bundled" if static_dir() else "not built (builder/player unavailable; "
                                                        "pil renderer only)"))
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exe = Path(p.chromium.executable_path)
        line(OK if exe.exists() else WARN,
             "headless chromium: " + ("installed" if exe.exists() else "missing (`code-deck setup`)"))
    except Exception as e:
        line(WARN, f"headless chromium: unavailable ({e})")
    raise typer.Exit(1 if problems else 0)


@app.command()
def version() -> None:
    typer.echo(__version__)


if __name__ == "__main__":
    app()
