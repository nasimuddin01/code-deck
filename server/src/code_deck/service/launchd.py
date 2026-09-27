"""macOS LaunchAgent management for the CODE DECK server.

The agent starts at login, restarts on crash (KeepAlive), and logs under
~/Library/Logs/code-deck/. ProgramArguments use the *current* interpreter with
`-m code_deck` so the plist points at exactly this installation (pipx venv or
dev venv) regardless of PATH.
"""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path

from ..config import HOME, IS_MAC, LAUNCHD_LABEL, LOG_DIR, ensure_dirs

PLIST_PATH = Path("~/Library/LaunchAgents").expanduser() / f"{LAUNCHD_LABEL}.plist"


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _require_mac() -> None:
    if not IS_MAC:
        raise RuntimeError("launchd service management is macOS-only; "
                           "on Linux use the Docker Compose target or a systemd unit")


def _launchctl(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, check=check)


def plist_dict(extra_args: list[str] | None = None) -> dict:
    path = os.environ.get("PATH", "")
    for p in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin",
              str(Path("~/.local/bin").expanduser())):
        if p not in path.split(":"):
            path = f"{path}:{p}" if path else p
    env = {"PATH": path, "HOME": str(Path.home())}
    # Values from a .env are NOT baked in: the service re-reads
    # ~/.config/code-deck/.env at start, so edits apply on restart. Only keys
    # explicitly exported in the installing shell are pinned.
    from ..config import ENV_PREFIX, FROM_FILES
    for k, v in os.environ.items():
        if k.startswith(ENV_PREFIX) and k not in FROM_FILES and k != "CODE_DECK_ENV_FILE" and v:
            env[k] = v
    return {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [sys.executable, "-m", "code_deck", "serve", *(extra_args or [])],
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 10,
        "WorkingDirectory": str(HOME),
        "StandardOutPath": str(LOG_DIR / "stdout.log"),
        "StandardErrorPath": str(LOG_DIR / "stderr.log"),
        "EnvironmentVariables": env,
    }


def _wait_unloaded(timeout: float = 10.0) -> None:
    """`bootout` is asynchronous; bootstrapping before the old job is gone
    fails with 'Bootstrap failed: 5: Input/output error'."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _launchctl("print", f"{_domain()}/{LAUNCHD_LABEL}").returncode != 0:
            return
        time.sleep(0.25)


def install(extra_args: list[str] | None = None) -> Path:
    _require_mac()
    ensure_dirs()
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _launchctl("bootout", f"{_domain()}/{LAUNCHD_LABEL}")  # ignore "not loaded"
    _wait_unloaded()
    with open(PLIST_PATH, "wb") as f:
        plistlib.dump(plist_dict(extra_args), f)
    last = ""
    for attempt in range(5):
        r = _launchctl("bootstrap", _domain(), str(PLIST_PATH))
        if r.returncode == 0:
            return PLIST_PATH
        last = r.stderr.strip() or r.stdout.strip()
        time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"launchctl bootstrap failed: {last}")


def uninstall() -> bool:
    _require_mac()
    _launchctl("bootout", f"{_domain()}/{LAUNCHD_LABEL}")
    if PLIST_PATH.exists():
        PLIST_PATH.unlink()
        return True
    return False


def restart() -> None:
    _require_mac()
    _launchctl("kickstart", "-k", f"{_domain()}/{LAUNCHD_LABEL}", check=True)


def status() -> dict:
    """{'installed': bool, 'loaded': bool, 'running': bool, 'pid': int|None}"""
    _require_mac()
    out = {"installed": PLIST_PATH.exists(), "loaded": False, "running": False, "pid": None}
    r = _launchctl("print", f"{_domain()}/{LAUNCHD_LABEL}")
    if r.returncode != 0:
        return out
    out["loaded"] = True
    seen_state = False
    for line in r.stdout.splitlines():
        line = line.strip()
        # the service's own `state = running|waiting` comes first; nested
        # endpoint blocks later print `state = active` and must not override it
        if line.startswith("state = ") and not seen_state:
            seen_state = True
            out["running"] = line.split("=", 1)[1].strip() == "running"
        elif line.startswith("pid = "):
            try:
                out["pid"] = int(line.split("=", 1)[1])
            except ValueError:
                pass
    return out


def log_files() -> list[Path]:
    return [LOG_DIR / "server.log", LOG_DIR / "stderr.log", LOG_DIR / "stdout.log"]
