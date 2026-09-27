"""push source: payload parsing, the hub, and the HTTP routes."""
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from code_deck.agents.payload import session_from, stats_from
from code_deck.agents.push import PushHub
from code_deck.agents.registry import AgentRegistry, SourceContext
from code_deck.agents.spec import parse_specs
from code_deck.server.app import AppContext, create_app
from code_deck.server.layout import LayoutStore
from code_deck.state.store import StateStore

NO_BUILTINS = {"claude-code": {"enabled": False}, "claude-max": {"enabled": False},
               "codex": {"enabled": False}}


def test_session_states_map_to_row_status():
    now = time.time()
    w = session_from({"id": "s1", "cwd": "/x/my-app", "state": "working"}, now)
    assert w.label == "my-app" and w.live and not w.needs_input
    q = session_from({"id": "s2", "state": "waiting"}, now)
    assert q.needs_input and q.attention_kind == "needs" and q.label == "s2"
    d = session_from({"id": "s3", "state": "done"}, now)
    assert d.needs_input and d.attention_kind == "idle"
    stale = session_from({"id": "s4", "state": "working", "last_active": now - 600}, now)
    assert not stale.live          # working but silent for 10 min: not shown as live
    with pytest.raises(ValueError):
        session_from({"id": "s5", "state": "sleeping"}, now)


def test_stats_from_sums_sessions_and_drops_stale():
    now = time.time()
    st = stats_from("Bot", {"quota_pct": 30, "sessions": [
        {"id": "a", "tokens_in": 100, "tokens_out": 10, "cost_usd": 0.5, "state": "working"},
        {"id": "b", "tokens_in": 50, "tokens_out": 5, "cost_usd": 0.25},
        {"id": "old", "last_active": now - 3600},
    ]}, now)
    assert [s.id for s in st.sessions] == ["a", "b"]
    assert (st.tokens_in, st.tokens_out, st.cost_usd, st.sessions_today) == (150, 15, 0.75, 2)
    assert st.quota_pct == 30 and st.active


def test_hub_persists_and_ends(tmp_path):
    path = tmp_path / "push.json"
    hub = PushHub(path)
    hub.upsert_session("bot", "s1", {"state": "working", "cwd": "/p/app"})
    hub.update_agent("bot", {"cost_usd": 2.5, "bogus": 1})
    again = PushHub(path).payload("bot")         # survives a restart
    assert again["cost_usd"] == 2.5 and "bogus" not in again
    assert again["sessions"][0]["id"] == "s1"
    assert hub.end_session("bot", "s1") and hub.payload("bot")["sessions"] == []


@pytest.fixture
def client(tmp_path):
    store = StateStore()
    ctx = AppContext(store=store, layouts=LayoutStore(tmp_path / "layout.json"))
    sctx = SourceContext()
    sctx.shared["push"] = PushHub(tmp_path / "push.json")
    specs = parse_specs({"agents": {**NO_BUILTINS, "declared": {"source": "push", "name": "Declared"},
                                    "scripted": {"source": "command", "command": "true"}}})
    reg = AgentRegistry(specs, sctx)
    woke = []
    ctx.sampler = SimpleNamespace(registry=reg, wake=lambda: woke.append(1))
    c = TestClient(create_app(ctx))
    c.reg, c.woke = reg, woke
    return c


def _tool(reg, agent_id):
    return next(t for t in reg.get_stats() if t.agent_id == agent_id)


def test_push_session_lifecycle(client):
    r = client.post("/api/agents/declared/sessions/abc", json={"state": "waiting", "cwd": "/w/api"})
    assert r.status_code == 200 and client.woke
    t = _tool(client.reg, "declared")
    assert t.name == "Declared" and t.sessions[0].label == "api" and t.sessions[0].needs_input
    client.delete("/api/agents/declared/sessions/abc")
    assert _tool(client.reg, "declared").sessions == []


def test_push_to_unknown_id_creates_agent(client):
    client.post("/api/agents/new-bot", json={"cost_usd": 1.25, "quota_pct": 40,
                                            "sessions": [{"id": "x", "state": "working"}]})
    t = _tool(client.reg, "new-bot")
    assert t.cost_usd == 1.25 and t.quota_pct == 40 and t.sessions[0].live and t.source == "push"


def test_push_rejects_bad_input(client):
    assert client.post("/api/agents/Bad%20Id", json={}).status_code == 400
    assert client.post("/api/agents/scripted", json={}).status_code == 409   # not a push agent
    assert client.post("/api/agents/declared/sessions/a", json={"state": "nope"}).status_code == 422
    assert client.post("/api/agents/declared", json={"quota_pct": 140}).status_code == 422
