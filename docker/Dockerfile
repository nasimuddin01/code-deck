# CODE DECK for Linux / Raspberry Pi hosts (USB passthrough works there).
# Build from the repo root:  docker compose -f docker/compose.yml up --build
#
# Stage 1: web app  ->  Stage 2: wheel (web bundled)  ->  Stage 3: runtime

FROM node:22-slim AS web
WORKDIR /src/web
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
COPY server/src/code_deck/layouts/ /src/server/src/code_deck/layouts/
RUN pnpm build

FROM python:3.12-slim-bookworm AS wheel
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /src/server
COPY server/ ./
COPY --from=web /src/web/dist/ ./src/code_deck/static/
RUN uv build --wheel -q

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    CODE_DECK_HOME=/data \
    CODE_DECK_OTLP_HOST=0.0.0.0 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN apt-get update && apt-get install -y --no-install-recommends libusb-1.0-0 && rm -rf /var/lib/apt/lists/*
COPY --from=wheel /src/server/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl \
 && python -m playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*
VOLUME ["/data"]
EXPOSE 8765 4318
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8765/api/health')" || exit 1
ENV CODE_DECK_HOST=0.0.0.0
CMD ["code-deck", "serve"]
