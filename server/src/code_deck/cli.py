"""`code-deck` command line."""
from __future__ import annotations

import json
import shutil
import socket
import sys
from pathlib import Path

import typer

from . import __version__, config

app = typer.Typer(help="CODE DECK — Claude Code + Codex dashboard on a TURZX USB screen.",
                  no_args_is_help=True, add_completion=False)
service_app = typer.Typer(help="Manage the background service (macOS launchd).",
                          no_args_is_help=True)
hooks_app = typer.Typer(help="Claude Code hook integration.", no_args_is_help=True)
env_app = typer.Typer(help="Claude Code telemetry environment.", no_args_is_help=True)
app.add_typer(service_app, name="service")
app.add_typer(hooks_app, name="hooks")
app.add_typer(env_app, name="env")

OK, BAD, WARN, INFO = "✓", "✗", "!", "·"


def _hook_command() -> str:
    """Absolute command Claude Code should run for the attention hook: the
    console-script shim next to this interpreter (stable under pipx), else
    `python -m`."""
    shim = Path(sys.executable).parent / "code-deck-hook"
    if shim.exists():
        return str(shim)
    return f'"{sys.executable}" -m code_deck.hooks.attention'


def _read_settings() -> dict | None:
    try:
        with open(config.CLAUDE_SETTINGS) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# -- serve ------------------------------------------------------------------

@app.command()
def serve(
    renderer: str = typer.Option("pil", help="pil (current) | chromium (coming)"),
    interval: float = typer.Option(config.DEFAULT_INTERVAL, help="seconds between polls"),
    brightness: int = typer.Option(config.DEFAULT_BRIGHTNESS, min=0, max=255,
                                   help="raw panel brightness param"),
    overlay: bool = typer.Option(True, help="full-screen banner when a session needs you"),
    overlay_seconds: float = typer.Option(config.DEFAULT_OVERLAY_SECONDS),
    no_device: bool = typer.Option(False, help="render to the preview file only"),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
) -> None:
    """Run the dashboard (foreground). `service install` runs this for you."""
    from .log import setup
    setup(verbose)
    if renderer != "pil":
        typer.echo(f"renderer '{renderer}' is not available yet; use --renderer pil", err=True)
        raise typer.Exit(2)
    from .render.legacy_loop import LegacyLoop
    LegacyLoop(interval=interval, brightness=brightness, overlay_enabled=overlay,
               overlay_seconds=overlay_seconds, no_device=no_device).run()


# -- service ----------------------------------------------------------------

@service_app.command("install")
def service_install(
    brightness: int = typer.Option(config.DEFAULT_BRIGHTNESS, min=0, max=255),
    overlay_seconds: float = typer.Option(config.DEFAULT_OVERLAY_SECONDS),
) -> None:
    """Install + start the launchd agent (starts at login, restarts on crash)."""
    from .service import launchd
    args = ["--brightness", str(brightness), "--overlay-seconds", str(overlay_seconds)]
    path = launchd.install(args)
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
    typer.echo(json.dumps({"hooks": {ev: entry for ev in config.HOOK_EVENTS}}, indent=2))


@env_app.command("print")
def env_print() -> None:
    """Print the `env` block that makes Claude Code export cost telemetry to us."""
    typer.echo(json.dumps({"env": config.TELEMETRY_ENV}, indent=2))


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
        missing = [k for k in config.TELEMETRY_ENV if k not in env]
        if not missing:
            line(OK, "telemetry env: all keys present")
        else:
            line(WARN, f"telemetry env missing {', '.join(missing)} (`code-deck env print`)")

    with socket.socket() as s:
        s.settimeout(0.3)
        bound = s.connect_ex(("127.0.0.1", config.OTLP_PORT)) == 0
    line(OK if bound else INFO,
         f"OTLP receiver port {config.OTLP_PORT}: " + ("listening" if bound else "not listening (starts with serve)"))

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

    line(INFO, "chromium renderer: not part of this release yet")
    raise typer.Exit(1 if problems else 0)


@app.command()
def version() -> None:
    typer.echo(__version__)


if __name__ == "__main__":
    app()
