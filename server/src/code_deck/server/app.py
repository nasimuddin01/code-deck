"""FastAPI application factory.

`AppContext` bundles the shared objects (store, layout store, settings hook);
routes reach it via `request.app.state.ctx`. Static assets (the built web app)
are served when present; otherwise `/` explains how to build them.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Callable

from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from ..state.store import StateStore
from .api import router, ws_state
from .layout import LayoutStore, Settings

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    store: StateStore
    layouts: LayoutStore
    # called when settings change (brightness, overlay); the device loop and
    # tracker subscribe by passing a callback
    settings_listeners: list[Callable[[Settings], None]] = field(default_factory=list)

    def apply_settings(self, settings: Settings) -> None:
        self.store.update_device(brightness=settings.brightness)
        for cb in list(self.settings_listeners):
            try:
                cb(settings)
            except Exception:
                log.exception("settings listener failed")


def static_dir() -> Path | None:
    p = Path(str(resources.files("code_deck").joinpath("static")))
    return p if (p / "index.html").exists() else None


def create_app(ctx: AppContext) -> FastAPI:
    app = FastAPI(title="CODE DECK", docs_url="/api/docs", redoc_url=None)
    app.state.ctx = ctx
    app.include_router(router)
    app.add_api_websocket_route("/ws/state", ws_state)

    static = static_dir()
    if static is not None:
        assets = static / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")
        for sub in ("fonts",):
            if (static / sub).exists():
                app.mount(f"/{sub}", StaticFiles(directory=static / sub), name=sub)

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):  # builder and player are client-side routes
            candidate = static / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def no_web():
            return PlainTextResponse(
                "CODE DECK server is running, but the web app is not built.\n"
                "API: /api/state  /api/layout  /ws/state\n"
                "Build the web app (see README) to enable the builder and player.\n",
                status_code=503)
    return app
