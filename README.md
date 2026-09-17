# CODE DECK

A desk dashboard for a **TURZX 3.5" USB smart screen** (320x480 portrait) that shows
live **Claude Code**, **Claude Max** and **Codex** usage: spend, weekly quota, active
sessions, and a "needs you" alert when an agent is waiting on you.

> Status: working prototype, being packaged into an installable tool with a
> drag-and-drop layout builder (see the v2 plan in the project notes). The
> current runner is `run_dashboard.py`.

## What's here

| Path | Purpose |
|---|---|
| `turzx/usbraw.py` | The display driver — raw USB bulk via pyusb/libusb (VID `1A86` PID `5722`). Full and partial-region draws. |
| `turzx/pixels.py` | RGB565LE conversion with a command-byte-safe LUT. |
| `dashboard/render.py` | PIL renderer for the 320x480 frame. |
| `dashboard/live.py` | Data layer: tails Claude Code / Codex transcripts, merges OTLP cost, Codex quota, attention flags. |
| `dashboard/otel_receiver.py` | In-process OTLP/http receiver (127.0.0.1:4318) for authoritative Claude Code cost. |
| `dashboard/codex_appserver.py` | JSON-RPC client to the Codex app-server for weekly rate limits. |
| `dashboard/attention_hook.py` | Claude Code hook script → per-session "needs you" / "turn ended" flags. |
| `run_dashboard.py` | The runner loop (render → push, overlay, auto-reconnect). |
| `docs/protocol/` | USB captures and the protocol report the driver was reverse-engineered from. |
| `tools/experiments/` | The hardware experiments that led to the working transport. |

## Why raw USB

The screen enumerates as a CDC serial device, but the macOS serial driver
corrupts frames. Driving the bulk endpoint directly with libusb is what works —
see `docs/protocol/turzx_protocol_report.md`.

## Running (current prototype)

```
brew install libusb
python -m venv .venv && .venv/bin/pip install pyusb pillow numpy
.venv/bin/python run_dashboard.py
```

Claude Code integration (both are pasted by you into `~/.claude/settings.json`;
this project never writes that file):

- **Cost telemetry** — add the OTLP env block (`CLAUDE_CODE_ENABLE_TELEMETRY=1`,
  `OTEL_METRICS_EXPORTER=otlp`, `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`,
  `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318`).
- **Attention hooks** — register `dashboard/attention_hook.py` on
  `Notification`, `Stop`, `UserPromptSubmit`, `SessionEnd`.

## License

MIT — see `LICENSE`. The vendor's Windows software is **not** part of this
repository.
