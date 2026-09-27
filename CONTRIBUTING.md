# Contributing

Thanks for looking under the hood. CODE DECK is small on purpose; most
contributions are new widgets, new data sources, or support for another
screen.

## Layout of the repo

| Path | What |
|---|---|
| `server/src/code_deck/` | Python package (`code-deck` CLI). `providers/` read Claude Code / Codex state, `state/` holds the shared store + samplers, `server/` is the FastAPI API, `render/` is the Chromium frame pipeline (+ the legacy PIL renderer), `turzx/` is the USB driver, `service/` the launchd agent. |
| `web/` | Vite + React app: `/` builder, `/player` what the device shows, `/preview` read-only frame. Widgets live in `web/src/widgets/`. |
| `docker/` | Compose target for Linux / Raspberry Pi. |
| `docs/protocol/` | USB captures and the protocol write-up. |
| `tools/experiments/` | The hardware experiments that led to the transport. Archival. |

## Dev setup

```
brew install libusb            # macOS; apt install libusb-1.0-0 on Linux
cd server && uv sync --group dev && uv run pytest
cd web && pnpm install && pnpm test
```

Run against the real screen from the checkout, with hot reload:

```
cd web && pnpm dev                                   # :5173
cd server && uv run code-deck serve --player-url http://127.0.0.1:5173/player?device=1
```

Without hardware: `uv run code-deck serve --no-device --mock` renders to
`~/.config/code-deck/preview.png`; `uv run code-deck render out.png --mock`
produces one frame and exits.

Ship a build into the installed service: `cd web && pnpm build:server`, then
`cd server && uv build && UV_VENV_CLEAR=1 pipx install --force dist/*.whl && code-deck service install`.

## Adding a widget

1. Create `web/src/widgets/MyWidget.tsx` exporting a `defineWidget({...})`:
   a zod `schema` for its props, `defaults`, `defaultSize`/`minSize`, a
   `category`, and the `Component`. Read live data through the selector hooks
   in `web/src/store/live.ts` (`useTool`, `useSystem`, …) — never the raw
   snapshot. Keep text positioned absolutely with the `.t` class so it lines
   up like the rest of the screen.
2. Register it in `web/src/registry/index.ts`. That is all: the builder's
   palette and props form are generated from the definition, and the player
   validates saved props against the schema (falling back to `defaults`, so a
   layout saved by an older version can never blank the device).
3. If it animates, bump `window.__cd.dirty` (see `lib/dirty.ts`) so the frame
   pipeline knows to screenshot; anything that changes pixels must.
4. `pnpm test` checks the registry (defaults satisfy the schema, sizes sane)
   and that the default layout still validates.

Remember the transport: a full 320x480 frame takes ~1.9 s to push, a small
rectangle a few ms. Widgets that change many pixels at once will feel slow.

## Adding an agent or a source type

Most agents need no code: `push`, `command`, `jsonl` and `otel` sources are
configured in `agents.toml` (see `docs/agents.md`). For a new source *type*,
write a factory `(spec, ctx) -> object with stats()` and register it with
`code_deck.agents.register_source()` in `server/src/code_deck/agents/`, or ship
it as a separate package through the `code_deck.sources` entry point. The
built-ins (`agents/builtin.py`) are the reference. Sources return the payload
shape in `agents/payload.py` or a `ToolStats`; the registry stamps id, name
and colour, and isolates failures.

Other snapshot sections (system stats and the like) are published by the
sampler threads in `state/`; mirror any new field in `web/src/types/state.ts`
(snake_case, same names) and expose a selector hook.

## Adding a setting

Settings are `CODE_DECK_*` variables. Add the entry to `ENV_SPEC` in
`server/src/code_deck/config.py`, read it there with `_env()` /
`_env_int()` / `_env_path()`, then regenerate the template:

```sh
cd server && uv run code-deck env example > ../.env.example
```

A test fails if `.env.example` drifts from `ENV_SPEC`. The setup wizard
(`code-deck init`, in `wizard.py`) writes the same format to
`~/.config/code-deck/.env`.

## Releasing

Bump the version in `server/pyproject.toml`, `server/src/code_deck/__init__.py`,
`web/package.json` and `menubar/Info.plist`, then push a tag (`v2.1.0`).
`.github/workflows/release.yml` builds the macOS app for Apple Silicon and
Intel with `scripts/package-macos.sh` and publishes a GitHub Release. Run
the script locally to test a build first.

## Ground rules

- Never commit the vendor's Windows software or anything from `turzx-win/`.
- Never commit a `.env`, personal paths, real usage numbers or screenshots of
  real sessions. Use `--mock` data for screenshots and examples.
- Never store or log credentials, tokens, or environment variable values. The
  CLI prints the Claude Code snippets for the user to paste; it does not
  write `~/.claude/settings.json`.
- Keep the device working after every commit: the PIL renderer stays as
  `--renderer pil` until the Chromium path has a release behind it.
- `uv run ruff check`, `uv run pytest`, `pnpm typecheck`, `pnpm test` should
  all pass; CI runs them plus a headless render.
