#!/usr/bin/env bash
# CODE DECK installer for a fresh clone (macOS or Linux).
#
#   ./install.sh            check prerequisites, build, install, then run the setup wizard
#   ./install.sh --yes      same, accepting every default (no prompts)
#   ./install.sh --check    only report what's missing; change nothing
#
# What it does:
#   1. checks python >= 3.11, pipx (or uv), node + pnpm, libusb
#   2. builds the React app into the Python package (the builder + device renderer)
#   3. builds the wheel and installs it with pipx  ->  `code-deck`, `code-deck-hook`
#   4. runs `code-deck init`: finds the screen, installs headless Chromium,
#      checks ports, shows the Claude Code snippets, writes ~/.config/code-deck/.env,
#      and offers to start the background service
set -euo pipefail

cd "$(dirname "$0")"
YES=""; CHECK=0
for a in "$@"; do
  case "$a" in
    --yes|-y) YES="--yes" ;;
    --check)  CHECK=1 ;;
    -h|--help) sed -n 2,14p "$0"; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$*"; MISSING=1; }
info() { printf '  · %s\n' "$*"; }
MISSING=0
OS="$(uname -s)"

bold "CODE DECK installer"

bold "[1] prerequisites"
PY=""
for c in python3 python3.13 python3.12 python3.11; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    PY="$c"; break
  fi
done
[ -n "$PY" ] && ok "python $("$PY" -c 'import platform; print(platform.python_version())')" \
             || bad "python >= 3.11 (macOS: brew install python · Linux: your package manager)"

if command -v pipx >/dev/null; then ok "pipx"
elif command -v uv >/dev/null; then ok "uv (will install with 'uv tool')"
else bad "pipx or uv (brew install pipx · or: curl -LsSf https://astral.sh/uv/install.sh | sh)"; fi

command -v node >/dev/null && ok "node $(node --version)" || bad "node >= 20 (https://nodejs.org or: brew install node)"
if command -v pnpm >/dev/null; then ok "pnpm $(pnpm --version)"
elif command -v corepack >/dev/null; then info "pnpm missing; will enable it via corepack"
else bad "pnpm (npm install -g pnpm)"; fi

LIBUSB=""
for p in /opt/homebrew/lib/libusb-1.0.dylib /usr/local/lib/libusb-1.0.dylib \
         /usr/lib/x86_64-linux-gnu/libusb-1.0.so.0 /usr/lib/aarch64-linux-gnu/libusb-1.0.so.0 \
         /usr/lib/libusb-1.0.so.0 /usr/lib64/libusb-1.0.so.0; do
  [ -e "$p" ] && { LIBUSB="$p"; break; }
done
if [ -n "$LIBUSB" ]; then ok "libusb $LIBUSB"
elif [ "$OS" = Darwin ]; then info "libusb missing; the setup wizard will offer 'brew install libusb'"
else info "libusb missing; install it: sudo apt install libusb-1.0-0 (the wizard re-checks)"; fi

if [ "$CHECK" = 1 ]; then
  [ "$MISSING" = 0 ] && bold "ready to install: ./install.sh" || bold "install the items marked ✗, then re-run"
  exit "$MISSING"
fi
[ "$MISSING" = 0 ] || { bold "install the items marked ✗, then re-run ./install.sh"; exit 1; }

if ! command -v pnpm >/dev/null; then
  COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack enable pnpm
fi

bold "[2] building the web app"
( cd web && pnpm install --frozen-lockfile --silent && pnpm build:server )
ok "bundled into server/src/code_deck/static"

bold "[3] installing the code-deck command"
rm -rf server/dist
if command -v uv >/dev/null; then
  ( cd server && uv build --wheel -q )
else
  "$PY" -m pip install --quiet build && ( cd server && "$PY" -m build --wheel -q )
fi
WHEEL="$(ls server/dist/*.whl | head -n 1)"
if command -v pipx >/dev/null; then
  # PIPX_DEFAULT_PYTHON rather than --python: pipx ignores --python with --force
  UV_VENV_CLEAR=1 PIPX_DEFAULT_PYTHON="$(command -v "$PY")" pipx install --force "$WHEEL"
else
  uv tool install --force --python "$PY" "$WHEEL"
fi
if ! command -v code-deck >/dev/null; then
  info "code-deck isn't on your PATH yet: run 'pipx ensurepath' (or 'uv tool update-shell') and open a new terminal"
  BIN="$HOME/.local/bin/code-deck"
else
  BIN="$(command -v code-deck)"
fi
ok "installed $("$BIN" version)"

# a running service still points at the files we just replaced: move it to the new build now,
# before the wizard, so it can never be left serving errors
if [ "$OS" = Darwin ] && [ -f "$HOME/Library/LaunchAgents/com.codedeck.server.plist" ]; then
  "$BIN" service install >/dev/null && ok "restarted the background service on the new build"
fi

bold "[4] setup wizard"
[ -t 0 ] || YES="--yes"      # no keyboard (run from another tool): accept defaults
exec "$BIN" init $YES
