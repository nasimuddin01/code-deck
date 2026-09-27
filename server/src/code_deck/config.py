"""Paths and defaults. Precedence everywhere: CLI flag > environment > .env > default.

Every setting is a ``CODE_DECK_*`` variable (see ``.env.example`` at the repo
root). They are read from the real environment first, then from a ``.env``
file, so the same names work for ``code-deck serve`` in a checkout, the
launchd service, Docker Compose and the menu bar app.

.env lookup (first file wins per key; the real environment always wins):
  1. ``$CODE_DECK_ENV_FILE`` if set
  2. ``./.env`` in the current directory (a repo checkout)
  3. ``~/.config/code-deck/.env`` (what ``code-deck init`` writes; the
     launchd service and menu bar app read this one)
Only ``CODE_DECK_*`` keys are loaded, so a project's unrelated .env is never
pulled into the process.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "code-deck"
LAUNCHD_LABEL = "com.codedeck.server"
IS_MAC = sys.platform == "darwin"
ENV_PREFIX = "CODE_DECK_"
USER_ENV_FILE = Path("~/.config/code-deck/.env").expanduser()


def parse_env_file(path: Path) -> dict[str, str]:
    """Minimal .env parser: KEY=VALUE lines, # comments, optional quotes,
    optional leading `export`. No interpolation."""
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        elif " #" in val:                      # trailing comment on an unquoted value
            val = val.split(" #", 1)[0].rstrip()
        if key:
            out[key] = val
    return out


FROM_FILES: set[str] = set()   # keys that came from a .env, not the real environment


def env_files() -> list[Path]:
    files = []
    if os.environ.get("CODE_DECK_ENV_FILE"):
        files.append(Path(os.environ["CODE_DECK_ENV_FILE"]).expanduser())
    files += [Path.cwd() / ".env", USER_ENV_FILE]
    return files


def load_env() -> list[Path]:
    """Copy CODE_DECK_* keys from the .env files into os.environ without
    overriding anything already set. Returns the files that were read."""
    used = []
    FROM_FILES.clear()
    for f in env_files():
        vals = parse_env_file(f)
        if not vals:
            continue
        used.append(f)
        for k, v in vals.items():
            if k.startswith(ENV_PREFIX) and k not in os.environ:
                os.environ[k] = v
                FROM_FILES.add(k)
    return used


LOADED_ENV_FILES = load_env()


def _env(name: str, default: str) -> str:
    v = os.environ.get(ENV_PREFIX + name, "").strip()
    return v or default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_path(name: str, default: str) -> Path:
    return Path(_env(name, default)).expanduser()


# -- where things live --------------------------------------------------------
HOME = _env_path("HOME", "~/.config/code-deck")          # layout.json, preview, cache
CACHE_DIR = HOME / "cache"
LOG_DIR = _env_path("LOG_DIR", "~/Library/Logs/code-deck" if IS_MAC else str(HOME / "logs"))
PREVIEW_PATH = HOME / "preview.png"   # mirror of the last frame pushed to the device

# Claude Code integration state lives under the Claude dir, not CODE_DECK_HOME:
# the hook Claude Code invokes writes attention flags there, and the OTLP
# receiver keeps its day totals alongside (see providers/).
CLAUDE_DIR = _env_path("CLAUDE_DIR", "~/.claude")
CLAUDE_SETTINGS = CLAUDE_DIR / "settings.json"
CLAUDE_PROJECTS = CLAUDE_DIR / "projects"
STATE_DIR = CLAUDE_DIR / "code-deck"                     # attention flags + otel day state
ATTENTION_DIR = STATE_DIR / "attention"
OTEL_STATE_PATH = STATE_DIR / "otel_state.json"
CODEX_DIR = _env_path("CODEX_DIR", "~/.codex")
AGENTS_FILE = _env_path("AGENTS_FILE", str(HOME / "agents.toml"))  # custom agents, see docs/agents.md
CODEX_APPSERVER_BIN = _env_path("CODEX_APPSERVER", str(CODEX_DIR / "plugins/.plugin-appserver/codex"))

# -- network ------------------------------------------------------------------
DEFAULT_HOST = _env("HOST", "127.0.0.1")                 # 0.0.0.0 exposes the builder on the LAN
DEFAULT_PORT = _env_int("PORT", 8765)
OTLP_HOST = _env("OTLP_HOST", "127.0.0.1")               # Docker sets 0.0.0.0
OTLP_PORT = _env_int("OTLP_PORT", 4318)
PLAYER_URL = _env("PLAYER_URL", "")                      # override the page Chromium renders

# -- rendering / device -------------------------------------------------------
# chromium renders the React player (what the builder edits); pil is the v1
# renderer kept as a fallback for one release
DEFAULT_RENDERER = _env("RENDERER", "chromium")
DEFAULT_BRIGHTNESS = _env_int("BRIGHTNESS", 39)          # raw device param (0-255), not percent
DEFAULT_INTERVAL = 10         # seconds between stats polls / PIL frames
DEFAULT_OVERLAY_SECONDS = 10


def claude_telemetry_env() -> dict[str, str]:
    """Claude Code telemetry the user pastes into ~/.claude/settings.json "env".
    Non-secret configuration; this tool prints it and never writes settings.json."""
    host = "127.0.0.1" if OTLP_HOST in ("0.0.0.0", "") else OTLP_HOST
    return {
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "OTEL_METRICS_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
        "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://{host}:{OTLP_PORT}",
        "OTEL_METRIC_EXPORT_INTERVAL": "10000",
    }


TELEMETRY_ENV = claude_telemetry_env()
# Claude Code hook events the attention script must be registered on.
HOOK_EVENTS = ("Notification", "Stop", "UserPromptSubmit", "SessionEnd")


def hook_command() -> str:
    """Absolute command Claude Code should run for the attention hook: the
    console-script shim next to this interpreter (stable under pipx), else
    `python -m`."""
    shim = Path(sys.executable).parent / "code-deck-hook"
    if shim.exists():
        return str(shim)
    return f'"{sys.executable}" -m code_deck.hooks.attention'


def ensure_dirs() -> None:
    for d in (HOME, CACHE_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)


# -- the documented settings ------------------------------------------------------
# One source of truth for .env.example, the setup wizard and `doctor`.
# (name without prefix, default shown to users, one-line description, section)
ENV_SPEC: tuple[tuple[str, str, str, str], ...] = (
    ("HOST", "127.0.0.1", "Address the builder/API binds to. 0.0.0.0 exposes it on your LAN.", "Server"),
    ("PORT", "8765", "Builder, API and player port.", "Server"),
    ("OTLP_HOST", "127.0.0.1", "Address the Claude Code telemetry receiver binds to (Docker: 0.0.0.0).", "Server"),
    ("OTLP_PORT", "4318", "Telemetry receiver port. Claude Code's OTEL endpoint must match.", "Server"),
    ("RENDERER", "chromium", "chromium (the React player) | pil (legacy) | none (API only).", "Rendering"),
    ("BRIGHTNESS", "39", "Panel brightness 0-255 until you set it in the builder.", "Rendering"),
    ("PLAYER_URL", "", "Render this URL instead of the bundled player, e.g. the Vite dev server.", "Rendering"),
    ("LIBUSB", "", "Full path to libusb-1.0 if it isn't found automatically.", "Device"),
    ("HOME", "~/.config/code-deck", "Layout, preview frame and cache.", "Paths"),
    ("LOG_DIR", "", "Log files. Default: ~/Library/Logs/code-deck on macOS, CODE_DECK_HOME/logs elsewhere.", "Paths"),
    ("AGENTS_FILE", "~/.config/code-deck/agents.toml", "Your own coding agents (see docs/agents.md).", "Paths"),
    ("CLAUDE_DIR", "~/.claude", "Claude Code's data folder (transcripts, settings.json).", "Paths"),
    ("CODEX_DIR", "~/.codex", "Codex's data folder (sessions, app-server).", "Paths"),
    ("CODEX_APPSERVER", "", "Codex app-server binary for live quota. Default: CODE_DECK_CODEX_DIR/plugins/.plugin-appserver/codex.", "Paths"),
    ("URL", "http://127.0.0.1:8765", "Where the macOS menu bar app finds the server.", "Menu bar app"),
)


def render_env_file(values: dict[str, str] | None = None, *, header: str = "") -> str:
    """A commented .env. Keys in `values` are written live; the rest stay as
    commented-out defaults so the file documents every option."""
    values = values or {}
    out = [header.rstrip() + "\n"] if header else []
    section = None
    for name, default, desc, sec in ENV_SPEC:
        if sec != section:
            out.append(f"\n# -- {sec} " + "-" * max(4, 60 - len(sec)) + "\n")
            section = sec
        out.append(f"# {desc}\n")
        key = ENV_PREFIX + name
        if key in values:
            out.append(f"{key}={values[key]}\n")
        else:
            out.append(f"# {key}={default}\n")
    return "".join(out).lstrip("\n")
