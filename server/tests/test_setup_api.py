"""GUI setup wizard backend: status shape, actions, safety."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from code_deck.server.app import AppContext, create_app
from code_deck.server.layout import LayoutStore
from code_deck.state.store import StateStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    from code_deck import config
    monkeypatch.setattr(config, "HOME", tmp_path)
    store = StateStore()
    ctx = AppContext(store=store, layouts=LayoutStore(tmp_path / "layout.json"))
    shown = []
    ctx.device_loop = SimpleNamespace(show_test=lambda s: shown.append(s))
    c = TestClient(create_app(ctx))
    c.shown = shown
    return c


def test_status_lists_every_step(client):
    st = client.get("/api/setup/status").json()
    ids = [s["id"] for s in st["steps"]]
    assert ids == ["libusb", "device", "renderer", "claude", "codex", "agents", "telemetry", "service"]
    for s in st["steps"]:
        assert s["status"] in ("ok", "warn", "error", "info") and s["title"] and "actions" in s
    assert st["done"] is False


def test_test_pattern_and_finish(client):
    r = client.post("/api/setup/actions/test-pattern")
    assert r.status_code == 200 and client.shown == [6]
    assert client.post("/api/setup/actions/finish").status_code == 200
    assert client.get("/api/setup/status").json()["done"] is True
    assert client.post("/api/setup/actions/nope").status_code == 404


def test_cross_site_writes_are_refused(client):
    evil = {"Origin": "https://evil.example"}
    assert client.post("/api/setup/actions/finish", headers=evil).status_code == 403
    assert client.post("/api/agents/x", json={}, headers=evil).status_code == 403
    ok = {"Origin": "http://127.0.0.1:5173"}
    assert client.post("/api/setup/actions/finish", headers=ok).status_code == 200
    assert client.get("/api/setup/status", headers=evil).status_code == 200   # reads are fine


def test_actions_are_local_only(client, monkeypatch):
    from code_deck.server import setup_api
    monkeypatch.setattr(setup_api, "LOCAL_HOSTS", {"127.0.0.1"})         # testclient isn't loopback
    assert client.post("/api/setup/actions/finish").status_code == 403
