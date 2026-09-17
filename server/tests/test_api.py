import pytest
from fastapi.testclient import TestClient

from code_deck.server.app import AppContext, create_app
from code_deck.server.layout import LayoutStore
from code_deck.state.store import StateStore


@pytest.fixture
def client(tmp_path):
    store = StateStore()
    store.update_device(brightness=39)
    ctx = AppContext(store=store, layouts=LayoutStore(tmp_path / "layout.json"))
    seen = []
    ctx.settings_listeners.append(seen.append)
    c = TestClient(create_app(ctx))
    c.store, c.seen = store, seen
    return c


def test_health_and_state(client):
    h = client.get("/api/health").json()
    assert h["ok"] and "version" in h and h["device_connected"] is False
    st = client.get("/api/state").json()
    assert set(st) >= {"rev", "ts", "tools", "system", "attention", "device", "layout_rev"}


def test_layout_roundtrip_and_reset(client):
    lay = client.get("/api/layout").json()
    assert lay["items"][0]["type"] == "Header"
    lay["items"][0]["x"] = 8
    lay["items"][0]["w"] = 304
    lay["settings"]["brightness"] = 77
    r = client.put("/api/layout", json=lay)
    assert r.status_code == 200
    assert client.get("/api/layout").json()["items"][0]["x"] == 8
    assert client.store.get("device")["brightness"] == 77       # settings applied
    assert client.store.get("layout_rev") == 1
    assert client.seen and client.seen[-1].brightness == 77
    client.post("/api/layout/reset")
    assert client.get("/api/layout").json()["items"][0]["x"] == 0
    assert client.store.get("layout_rev") == 2


def test_layout_rejects_out_of_bounds(client):
    lay = client.get("/api/layout").json()
    lay["items"][0]["h"] = 481
    assert client.put("/api/layout", json=lay).status_code == 422


def test_brightness_endpoint_persists(client):
    assert client.post("/api/device/brightness", json={"value": 200}).status_code == 200
    assert client.get("/api/layout").json()["settings"]["brightness"] == 200
    assert client.store.get("device")["brightness"] == 200
    assert client.post("/api/device/brightness", json={"value": 999}).status_code == 422


def test_websocket_sends_snapshot_then_changes(client):
    with client.websocket_connect("/ws/state") as ws:
        first = ws.receive_json()
        assert "rev" in first
        client.store.publish("system", {"cpu_pct": 42})
        nxt = ws.receive_json()
        assert nxt["rev"] > first["rev"] and nxt["system"]["cpu_pct"] == 42


def test_no_web_build_explains(client):
    r = client.get("/")
    assert r.status_code in (503, 200)  # 503 without a built web app
