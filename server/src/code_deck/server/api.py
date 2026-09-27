"""HTTP + WebSocket API."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

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


@router.get("/agents")
def list_agents(request: Request) -> list[dict]:
    """Every agent: built-ins, agents.toml entries and on-the-fly pushed ones."""
    return _ctx(request).store.get("agents")


class SessionPush(BaseModel):
    label: str | None = Field(None, max_length=80)
    cwd: str | None = Field(None, max_length=1024)
    model: str | None = Field(None, max_length=80)
    state: Literal["working", "waiting", "done", "idle"] | None = None
    tokens_in: int | None = Field(None, ge=0)
    tokens_out: int | None = Field(None, ge=0)
    cost_usd: float | None = Field(None, ge=0)
    last_active: float | None = None


class SessionPushWithId(SessionPush):
    id: str = Field(min_length=1, max_length=128)


class AgentPush(BaseModel):
    model: str | None = Field(None, max_length=80)
    cost_usd: float | None = Field(None, ge=0)
    tokens_in: int | None = Field(None, ge=0)
    tokens_out: int | None = Field(None, ge=0)
    sessions_today: int | None = Field(None, ge=0)
    quota_pct: float | None = Field(None, ge=0, le=100)
    quota_resets_at: float | None = None
    note: str | None = Field(None, max_length=40)
    activity_24h: list[float] | None = Field(None, max_length=24)
    cost_estimated: bool | None = None
    sessions: list[SessionPushWithId] | None = None   # replaces the session list when given


def _push_target(request: Request, agent_id: str):
    """(hub, sampler) for a push to `agent_id`, creating the agent if new."""
    from ..agents.push import push_hub
    from ..agents.spec import ID_RE
    sampler = _ctx(request).sampler
    if sampler is None or sampler.registry is None:
        raise HTTPException(503, "agents are unavailable (mock mode)")
    if not ID_RE.match(agent_id):
        raise HTTPException(400, "agent id: lowercase letters, digits, - or _ (max 32)")
    spec = sampler.registry.ensure_agent(agent_id)
    if spec.source != "push":
        raise HTTPException(409, f"agent {agent_id!r} uses source {spec.source!r}; "
                                 f"only push agents accept pushes")
    return push_hub(sampler.registry.ctx), sampler


@router.post("/agents/{agent_id}")
def push_agent(request: Request, agent_id: str, body: AgentPush) -> dict:
    hub, sampler = _push_target(request, agent_id)
    data = body.model_dump(exclude_none=True)
    sessions = data.pop("sessions", None)
    hub.update_agent(agent_id, data, sessions)
    sampler.wake()
    return {"ok": True, "agent": agent_id}


@router.post("/agents/{agent_id}/sessions/{session_id}")
def push_session(request: Request, agent_id: str, session_id: str, body: SessionPush) -> dict:
    if not 0 < len(session_id) <= 128:
        raise HTTPException(400, "session id must be 1-128 characters")
    hub, sampler = _push_target(request, agent_id)
    hub.upsert_session(agent_id, session_id, body.model_dump(exclude_none=True))
    sampler.wake()
    return {"ok": True, "agent": agent_id, "session": session_id}


@router.delete("/agents/{agent_id}/sessions/{session_id}")
def end_session(request: Request, agent_id: str, session_id: str) -> dict:
    hub, sampler = _push_target(request, agent_id)
    gone = hub.end_session(agent_id, session_id)
    sampler.wake()
    return {"ok": True, "removed": gone}


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
