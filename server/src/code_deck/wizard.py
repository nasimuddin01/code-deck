"""`code-deck init` — the interactive first-run setup wizard.

Walks a new user from "just installed" to "screen is live":

  1. libusb           find it; on macOS offer `brew install libusb`
  2. the screen       detect the TURZX panel (VID 1A86 PID 5722), wait for a
                      replug, and push a test frame so they *see* it work
  3. renderer         install the headless Chromium the React player needs
  4. ports            check 8765 / 4318, pick free ones if taken
  5. Claude Code      detect it; show the hooks + telemetry blocks to paste
                      (copied to the clipboard on request — settings.json is
                      never written by this tool)
  6. Codex            detect it
  7. .env             write ~/.config/code-deck/.env with the choices
  8. service          install the launchd agent (macOS) and open the builder

Every step is skippable, and `--yes` accepts the defaults non-interactively
(CI, Docker, dotfiles). Nothing here stores credentials: the .env holds only
ports, paths and renderer choices.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import typer

from . import config

OK, BAD, WARN, INFO = "✓", "✗", "!", "·"


class Wizard:
    def __init__(self, *, yes: bool, env_file: Path) -> None:
        self.yes = yes
        self.env_file = env_file
        self.values: dict[str, str] = dict(config.parse_env_file(env_file))
        self.notes: list[str] = []       # things the user still has to do
        self.step_no = 0

    # -- io helpers -------------------------------------------------------------
    def step(self, title: str) -> None:
        self.step_no += 1
        typer.secho(f"\n[{self.step_no}] {title}", bold=True)

    def say(self, mark: str, msg: str) -> None:
        color = {OK: "green", BAD: "red", WARN: "yellow"}.get(mark)
        typer.secho(f"  {mark} {msg}", fg=color)

    def confirm(self, question: str, default: bool = True) -> bool:
        if self.yes:
            return default
        return typer.confirm(f"  {question}", default=default)

    def ask(self, question: str, default: str) -> str:
        if self.yes:
            return default
        return typer.prompt(f"  {question}", default=default)

    def run(self, cmd: list[str]) -> bool:
        self.say(INFO, "$ " + " ".join(cmd))
        return subprocess.run(cmd).returncode == 0

    # -- steps --------------------------------------------------------------------
    def libusb(self) -> bool:
        from .turzx import libusb
        self.step("libusb (talks to the screen over USB)")
        path = libusb.find_libusb()
        if path:
            self.say(OK, f"found {path}")
            return True
        self.say(BAD, "libusb-1.0 not found")
        if config.IS_MAC and shutil.which("brew"):
            if (self.confirm("Install it now with Homebrew (brew install libusb)?")
                    and self.run(["brew", "install", "libusb"]) and libusb.find_libusb()):
                self.say(OK, f"installed {libusb.find_libusb()}")
                return True
        elif sys.platform.startswith("linux"):
            self.say(INFO, "install it with: sudo apt install libusb-1.0-0  (or your distro's equivalent)")
        custom = "" if self.yes else typer.prompt(
            "  Path to libusb-1.0 if you have it somewhere else (Enter to skip)",
            default="", show_default=False)
        if custom and Path(custom).expanduser().exists():
            self.values["CODE_DECK_LIBUSB"] = str(Path(custom).expanduser())
            os.environ["CODE_DECK_LIBUSB"] = self.values["CODE_DECK_LIBUSB"]
            self.say(OK, f"using {custom}")
            return True
        self.notes.append(f"Install libusb ({libusb.INSTALL_HINT}), then run `code-deck init` again.")
        return False

    def device(self, have_libusb: bool) -> None:
        self.step("TURZX 3.5\" screen")
        if not have_libusb:
            self.say(WARN, "skipped: needs libusb")
            return
        from .turzx.usbraw import PID, VID, find_device
        self.say(INFO, f"looking for USB device {VID:04x}:{PID:04x} (WCH USB controller inside the panel)")
        dev = find_device()
        while dev is None:
            self.say(WARN, "not found. Plug the screen into a data-capable USB port (not a charge-only cable).")
            if self.yes or not self.confirm("Plugged in? Check again", default=True):
                self.notes.append("Plug in the screen; the service picks it up automatically, no restart needed.")
                return
            time.sleep(1.5)
            dev = find_device()
        self.say(OK, "screen detected")
        if self._service_running():
            self.say(INFO, "the CODE DECK service is already driving it, so no test frame (it's live).")
            return
        if self.confirm("Show a test frame on the screen?"):
            self._test_frame()

    def _test_frame(self) -> None:
        from PIL import Image, ImageDraw, ImageFont

        from .turzx.usbraw import NATIVE_H, NATIVE_W, UsbRaw
        img = Image.new("RGB", (NATIVE_W, NATIVE_H), (26, 26, 25))
        d = ImageDraw.Draw(img)
        try:
            big, small = ImageFont.load_default(size=34), ImageFont.load_default(size=16)
        except TypeError:                       # Pillow < 10.1
            big = small = ImageFont.load_default()
        d.text((24, 60), "CODE DECK", fill=(236, 236, 232), font=big)
        d.text((24, 108), "setup check", fill=(150, 150, 145), font=small)
        for i, c in enumerate([(217, 89, 38), (154, 111, 240), (57, 135, 229)]):
            d.rounded_rectangle((24, 170 + i * 70, 296, 220 + i * 70), radius=12, fill=c)
        d.text((24, 400), "if you can read this,", fill=(150, 150, 145), font=small)
        d.text((24, 424), "the USB transport works", fill=(74, 163, 255), font=small)
        try:
            scr = UsbRaw()
            try:
                scr.init(config.DEFAULT_BRIGHTNESS)
                scr.draw(img)
            finally:
                scr.close()
        except Exception as e:                  # busy port, permissions, flaky cable
            self.say(BAD, f"couldn't draw: {e}")
            hint = ("close any app holding /dev/cu.usbmodem* (the vendor app, a serial monitor)"
                    if config.IS_MAC else "check udev permissions for 1a86:5722 or run once with sudo")
            self.notes.append(f"Test frame failed: {hint}, then run `code-deck init` again.")
            return
        if self.yes or self.confirm("Do you see 'CODE DECK' and three coloured bars?"):
            self.say(OK, "transport works")
        else:
            self.say(WARN, "noted. Try another cable/port; `code-deck doctor` shows more.")
            self.notes.append("The test frame didn't appear: try a different USB cable or port.")

    def chromium(self) -> None:
        self.step("renderer (headless Chromium draws the React player)")
        if self._chromium_installed():
            self.say(OK, "already installed")
            return
        if self.confirm("Download it now (one time)?"):
            cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
            if sys.platform.startswith("linux"):
                cmd.append("--with-deps")
            if self.run(cmd):
                self.say(OK, "installed")
                return
        self.notes.append("Install the renderer: `code-deck setup`.")

    def ports(self) -> None:
        self.step("ports")
        for key, label, current in (("CODE_DECK_PORT", "builder / API", config.DEFAULT_PORT),
                                    ("CODE_DECK_OTLP_PORT", "Claude Code telemetry", config.OTLP_PORT)):
            if not _port_busy(current) or self._service_running():
                self.say(OK, f"{label}: {current}")
                continue
            alt = _next_free(current + 1)
            self.say(WARN, f"{label}: {current} is taken by another program")
            chosen = self.ask(f"Use port {alt} instead?", str(alt))
            self.values[key] = chosen
            os.environ[key] = chosen
            if key == "CODE_DECK_PORT":
                self.values["CODE_DECK_URL"] = f"http://127.0.0.1:{chosen}"
            self.say(OK, f"{label}: {chosen}")

    def claude(self) -> None:
        self.step("Claude Code")
        if not config.CLAUDE_DIR.exists():
            self.say(INFO, f"not found at {config.CLAUDE_DIR} (set CODE_DECK_CLAUDE_DIR if it lives elsewhere)")
            return
        self.say(OK, f"found {config.CLAUDE_DIR}")
        settings = _read_json(config.CLAUDE_SETTINGS) or {}
        hook_cmd = config.hook_command()
        hooks = settings.get("hooks", {}) or {}
        missing_hooks = [ev for ev in config.HOOK_EVENTS
                         if not any("code-deck-hook" in h.get("command", "") or hook_cmd in h.get("command", "")
                                    for m in hooks.get(ev) or [] if isinstance(m, dict)
                                    for h in m.get("hooks") or [] if isinstance(h, dict))]
        env = settings.get("env", {}) or {}
        # the endpoint must match *this* install's port
        want_env = config.claude_telemetry_env()
        if "CODE_DECK_OTLP_PORT" in self.values:
            want_env["OTEL_EXPORTER_OTLP_ENDPOINT"] = f"http://127.0.0.1:{self.values['CODE_DECK_OTLP_PORT']}"
        missing_env = {k: v for k, v in want_env.items() if env.get(k) != v}

        if not missing_hooks:
            self.say(OK, "hooks registered (needs-you / turn-ended status)")
        if not missing_env:
            self.say(OK, "telemetry enabled (authoritative $ spend)")
        if not missing_hooks and not missing_env:
            return

        block: dict = {}
        if missing_hooks:
            entry = [{"hooks": [{"type": "command", "command": hook_cmd}]}]
            block["hooks"] = dict.fromkeys(config.HOOK_EVENTS, entry)
        if missing_env:
            block["env"] = want_env
        text = json.dumps(block, indent=2)
        what = " and ".join(x for x, m in (("hooks", missing_hooks), ("telemetry env", missing_env)) if m)
        self.say(WARN, f"{what} not set up yet. Merge this into {config.CLAUDE_SETTINGS}:")
        typer.echo("\n".join("    " + ln for ln in text.splitlines()))
        self.say(INFO, "code-deck never edits that file itself; it's yours.")
        if shutil.which("pbcopy") and self.confirm("Copy it to the clipboard?"):
            subprocess.run(["pbcopy"], input=text.encode(), check=False)
            self.say(OK, "copied")
        self.notes.append(f"Paste the {what} block into {config.CLAUDE_SETTINGS}; "
                          "only sessions started afterwards report cost.")

    def codex(self) -> None:
        self.step("Codex")
        if not config.CODEX_DIR.exists():
            self.say(INFO, f"not found at {config.CODEX_DIR} (optional; set CODE_DECK_CODEX_DIR if elsewhere)")
            return
        self.say(OK, f"found {config.CODEX_DIR}")
        if config.CODEX_APPSERVER_BIN.exists():
            self.say(OK, "app-server present: live weekly quota")
        else:
            self.say(INFO, "no app-server: quota is read from session files instead")

    def write_env(self) -> None:
        self.step(f"save settings to {self.env_file}")
        header = ("# CODE DECK settings, written by `code-deck init`.\n"
                  "# Uncomment a line to change it; restart with `code-deck service restart`.\n"
                  "# No secrets belong here: it's ports, paths and renderer choices.")
        text = config.render_env_file(self.values, header=header)
        if self.env_file.exists() and self.env_file.read_text() == text:
            self.say(OK, "unchanged")
            return
        if self.env_file.exists() and not self.confirm("Overwrite the existing file?", default=bool(self.values)):
            self.say(INFO, "kept the existing file")
            return
        self.env_file.parent.mkdir(parents=True, exist_ok=True)
        self.env_file.write_text(text)
        live = [k for k in self.values if k.startswith(config.ENV_PREFIX)]
        self.say(OK, "saved" + (f" ({', '.join(live)})" if live else " (all defaults, documented)"))

    def service(self) -> None:
        self.step("background service")
        if not config.IS_MAC:
            self.say(INFO, "Linux: run it with Docker Compose (docker/compose.yml) or `code-deck serve`.")
            return
        from .service import launchd
        if config.is_dev_checkout() and self.yes:
            self.say(WARN, "running from a development checkout: not installing the service "
                           "automatically (it would point at this checkout)")
            self.notes.append("Install the service from your installed copy: `code-deck service install`.")
            return
        if self.confirm("Install it so CODE DECK starts at login and restarts on crash?"):
            try:
                launchd.install()
                self.say(OK, "installed and started")
            except Exception as e:
                self.say(BAD, f"install failed: {e}")
                self.notes.append("Install the service: `code-deck service install`.")
                return
            port = self.values.get("CODE_DECK_PORT", str(config.DEFAULT_PORT))
            url = f"http://127.0.0.1:{port}/"
            if not self.yes and self.confirm(f"Open the layout builder ({url})?"):
                time.sleep(2)
                webbrowser.open(url)
        else:
            self.notes.append("Start it when you're ready: `code-deck service install` (or `code-deck serve`).")

    # -- helpers ------------------------------------------------------------------
    def _service_running(self) -> bool:
        if not config.IS_MAC:
            return False
        try:
            from .service import launchd
            return bool(launchd.status().get("running"))
        except Exception:
            return False

    @staticmethod
    def _chromium_installed() -> bool:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                return Path(p.chromium.executable_path).exists()
        except Exception:
            return False

    def finish(self) -> None:
        typer.secho("\nDone." if not self.notes else "\nAlmost there. Still to do:", bold=True)
        for n in self.notes:
            typer.echo(f"  - {n}")
        typer.echo("\n`code-deck doctor` re-checks everything; `code-deck init` is safe to re-run.")
        typer.echo("Use other coding agents too? Add them in agents.toml: see docs/agents.md "
                   "(`code-deck agents list` shows what's registered).")


def _port_busy(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _next_free(start: int) -> int:
    p = start
    while _port_busy(p) and p < start + 100:
        p += 1
    return p


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def run(yes: bool = False, env_file: Path | None = None) -> None:
    typer.secho("CODE DECK setup", bold=True)
    if not yes and not sys.stdin.isatty():
        # e.g. run from another tool or a `!` prompt: prompts would read EOF and abort
        typer.echo("No keyboard input available, so every default is accepted (same as --yes).")
        yes = True
    typer.echo("Gets the TURZX screen, the renderer and Claude Code/Codex wired up. "
               "Every step can be skipped and re-run later.")
    w = Wizard(yes=yes, env_file=env_file or config.USER_ENV_FILE)
    have_usb = w.libusb()
    w.device(have_usb)
    w.chromium()
    w.ports()
    w.claude()
    w.codex()
    w.write_env()
    w.service()
    w.finish()
