# CODE DECK task runner — https://github.com/casey/just

set shell := ["zsh", "-cu"]

# run the server test-suite
test:
    cd server && uv sync --group dev -q && uv run pytest -q

# lint the server
lint:
    cd server && uv sync --group dev -q && uv run ruff check src tests

# build the web app into the python package (server/src/code_deck/static)
web-build:
    cd web && pnpm install --silent && pnpm build:server

# web tests + typecheck
web-test:
    cd web && pnpm install --silent && pnpm typecheck && pnpm test

# build the wheel (with the web app inside) into server/dist
wheel: web-build
    cd server && rm -rf dist && uv build -q

# build + (re)install into pipx, then restart the service if installed
install-local: wheel
    # UV_VENV_CLEAR: pipx's uv backend refuses to recreate an existing venv otherwise
    UV_VENV_CLEAR=1 pipx install --force server/dist/*.whl
    code-deck service status >/dev/null 2>&1 && code-deck service restart || true

# run in the foreground from the dev checkout
serve *ARGS:
    cd server && uv run code-deck serve {{ARGS}}

# macOS menu bar app (swiftc; Command Line Tools are enough)
menubar:
    ./menubar/build.sh

menubar-install:
    ./menubar/build.sh --install
