"""HTTP + WebSocket API."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError

from .. import __version__
from .layout import Layout

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

WS_COALESCE_S = 0.25   # at most one push per 250 ms
WS_HEARTBEAT_S = 15.0  # resend even if nothing changed (keeps proxies/tabs alive)


def _ctx(request: Request | WebSocket) -> Any:
    return request.app.state.ctx


@router.get("/health")
def health(request: Request) -> dict:
    ctx = _ctx(request)
    dev = ctx.store.get("device")
    return {"ok": True, "version": __version__,
            "device_connected": dev["connected"], "chromium_ok": dev["chromium_ok"]}


@router.get("/state")
def state(request: Request) -> dict:
    return _ctx(request).store.snapshot()


@router.get("/layout")
def get_layout(request: Request) -> dict:
    return _ctx(request).layouts.load().model_dump()


@router.put("/layout")
def put_layout(request: Request, layout: Layout) -> dict:
    ctx = _ctx(request)
    ctx.layouts.save(layout)
    ctx.apply_settings(layout.settings)
    ctx.store.publish("layout_rev", ctx.layouts.rev)
    return layout.model_dump()


@router.post("/layout/reset")
def reset_layout(request: Request) -> dict:
    ctx = _ctx(request)
    layout = ctx.layouts.reset()
    ctx.apply_settings(layout.settings)
    ctx.store.publish("layout_rev", ctx.layouts.rev)
    return layout.model_dump()


class Brightness(BaseModel):
    value: int = Field(ge=0, le=255)


@router.post("/device/brightness")
def set_brightness(request: Request, body: Brightness) -> dict:
    ctx = _ctx(request)
    layout = ctx.layouts.load()
    layout.settings.brightness = body.value
    try:
        ctx.layouts.save(layout)
    except ValidationError as e:  # pragma: no cover - settings are already validated
        raise HTTPException(400, str(e)) from e
    ctx.apply_settings(layout.settings)
    ctx.store.publish("layout_rev", ctx.layouts.rev)
    return {"brightness": body.value}


async def ws_state(ws: WebSocket) -> None:
    """Snapshot on connect, then a fresh snapshot whenever the store changes
    (coalesced), plus a heartbeat. Mounted at /ws/state by app.py."""
    store = _ctx(ws).store
    await ws.accept()
    last_rev = -1
    try:
        while True:
            changed = await asyncio.to_thread(store.wait_for_change, last_rev, WS_HEARTBEAT_S)
            if changed:
                await asyncio.sleep(WS_COALESCE_S)
            snap = store.snapshot()
            last_rev = snap["rev"]
            await ws.send_json(snap)
    except (WebSocketDisconnect, RuntimeError):
        return
