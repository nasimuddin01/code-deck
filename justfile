# CODE DECK task runner — https://github.com/casey/just

set shell := ["zsh", "-cu"]

# run the server test-suite
test:
    cd server && uv sync --group dev -q && uv run pytest -q

# lint the server
lint:
    cd server && uv sync --group dev -q && uv run ruff check src tests

# build the wheel into server/dist
wheel:
    cd server && rm -rf dist && uv build -q

# build + (re)install into pipx, then restart the service if installed
install-local: wheel
    # UV_VENV_CLEAR: pipx's uv backend refuses to recreate an existing venv otherwise
    UV_VENV_CLEAR=1 pipx install --force server/dist/*.whl
    code-deck service status >/dev/null 2>&1 && code-deck service restart || true

# run in the foreground from the dev checkout
serve *ARGS:
    cd server && uv run code-deck serve {{ARGS}}
