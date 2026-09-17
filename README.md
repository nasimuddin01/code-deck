# CODE DECK

A desk dashboard for a **TURZX 3.5" USB smart screen** (320x480 portrait) that shows
live **Claude Code**, **Claude Max** and **Codex** usage: spend, weekly quota, active
sessions, and a "needs you" alert when an agent is waiting on you.

> Status: v2 in progress. The screen is rendered by a React app (`/player`)
> screenshotted with headless Chromium and pushed over USB as dirty
> rectangles; the drag-and-drop layout builder lands next.

## Install (macOS)

```
brew install libusb
pipx install ./server        # or the wheel from server/dist once released
code-deck setup              # one-time: headless Chromium for the renderer
code-deck doctor             # libusb, device, hooks, telemetry, service
code-deck service install    # launchd agent: starts at login, restarts on crash
```

`code-deck serve` runs it in the foreground instead (`--renderer pil` = the v1
PIL renderer, kept as a fallback). Logs live in `~/Library/Logs/code-deck/`;
the last frame is mirrored to `~/.config/code-deck/preview.png`. The live
preview page is `http://127.0.0.1:8765/` and the raw player `…/player`.

How it draws: the React player marks itself dirty on every change (data,
clock, layout); the Python side polls that counter, screenshots only then,
diffs against the previous frame and pushes just the changed rectangle. A
ticking seconds digit is a 5x7 px push (~8 ms); a full frame is ~1.9 s, which
is the panel's transport limit.

Claude Code integration — both blocks are printed for **you** to paste into
`~/.claude/settings.json`; this tool never writes that file:

- `code-deck env print` — telemetry env so Claude Code exports authoritative
  cost to the built-in OTLP receiver on `127.0.0.1:4318`.
- `code-deck hooks print` — registers the `code-deck-hook` script on
  `Notification`, `Stop`, `UserPromptSubmit`, `SessionEnd` for the
  "needs you" / "turn ended" session status.

Docker is not used on macOS (no USB passthrough); a Compose target for
Linux / Raspberry Pi is planned.

## What's here

| Path | Purpose |
|---|---|
| `server/src/code_deck/turzx/usbraw.py` | The display driver — raw USB bulk via pyusb/libusb (VID `1A86` PID `5722`). Full and partial-region draws. |
| `server/src/code_deck/turzx/pixels.py` | RGB565LE conversion with a command-byte-safe LUT. |
| `server/src/code_deck/render/pil_legacy.py` | v1 PIL renderer for the 320x480 frame (to be replaced by the React player). |
| `server/src/code_deck/providers/live.py` | Data layer: tails Claude Code / Codex transcripts, merges OTLP cost, Codex quota, attention flags. |
| `server/src/code_deck/providers/otel_receiver.py` | In-process OTLP/http receiver for authoritative Claude Code cost. |
| `server/src/code_deck/providers/codex_appserver.py` | JSON-RPC client to the Codex app-server for weekly rate limits. |
| `server/src/code_deck/hooks/attention.py` | The `code-deck-hook` Claude Code hook → per-session attention flags. |
| `server/src/code_deck/state/attention.py` | Decides when a session's "needs you" raises the full-screen overlay. |
| `server/src/code_deck/service/launchd.py` | macOS LaunchAgent install/status. |
| `docs/protocol/` | USB captures and the protocol report the driver was reverse-engineered from. |
| `tools/experiments/` | The hardware experiments that led to the working transport. |

## Why raw USB

The screen enumerates as a CDC serial device, but the macOS serial driver
corrupts frames. Driving the bulk endpoint directly with libusb is what works —
see `docs/protocol/turzx_protocol_report.md`.

## Development

```
cd server && uv sync --group dev && uv run pytest
cd web && pnpm install && pnpm test && pnpm build:server   # builds into server/src/code_deck/static
uv run code-deck serve --no-device      # renders to the preview file only
uv run code-deck render out.png --mock  # one frame, no device (CI golden)
```

Hot reload on the device: `pnpm dev` in `web/`, then
`code-deck serve --player-url http://127.0.0.1:5173/player?device=1`.

## License

MIT — see `LICENSE`. The vendor's Windows software is **not** part of this
repository.
