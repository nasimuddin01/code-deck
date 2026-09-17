"""Paths and defaults. Precedence everywhere: CLI flag > environment > default."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "code-deck"
LAUNCHD_LABEL = "com.codedeck.server"
IS_MAC = sys.platform == "darwin"

HOME = Path(os.environ.get("CODE_DECK_HOME", "~/.config/code-deck")).expanduser()
CACHE_DIR = HOME / "cache"
LOG_DIR = Path("~/Library/Logs/code-deck").expanduser() if IS_MAC else HOME / "logs"
PREVIEW_PATH = HOME / "preview.png"   # mirror of the last frame pushed to the device

# Claude Code integration state lives under ~/.claude, not CODE_DECK_HOME: the
# hook script Claude Code invokes writes attention flags there, and the OTLP
# receiver keeps its day totals alongside (see providers/).
CLAUDE_DIR = Path("~/.claude").expanduser()
CLAUDE_SETTINGS = CLAUDE_DIR / "settings.json"
CODEX_APPSERVER_BIN = Path("~/.codex/plugins/.plugin-appserver/codex").expanduser()

DEFAULT_PORT = int(os.environ.get("CODE_DECK_PORT", "8765"))
# chromium renders the React player (what the builder edits); pil is the v1
# renderer kept as a fallback for one release
DEFAULT_RENDERER = os.environ.get("CODE_DECK_RENDERER", "chromium")
OTLP_PORT = 4318
DEFAULT_BRIGHTNESS = 39       # raw device param (0-255), not percent
DEFAULT_INTERVAL = 10         # seconds between stats polls / PIL frames
DEFAULT_OVERLAY_SECONDS = 10

# Claude Code telemetry the user pastes into ~/.claude/settings.json "env".
# Non-secret configuration; this tool prints it and never writes settings.json.
TELEMETRY_ENV = {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
    "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://127.0.0.1:{OTLP_PORT}",
    "OTEL_METRIC_EXPORT_INTERVAL": "10000",
}
# Claude Code hook events the attention script must be registered on.
HOOK_EVENTS = ("Notification", "Stop", "UserPromptSubmit", "SessionEnd")


def ensure_dirs() -> None:
    for d in (HOME, CACHE_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
