"""jsonl and otel sources."""
import json
import os
import time
from types import SimpleNamespace

import pytest

from code_deck.agents.jsonl import JsonlSource, get_path, parse_ts
from code_deck.agents.otel import OtelSource
from code_deck.agents.registry import SourceContext
from code_deck.agents.spec import AgentSpec


def test_get_path_and_parse_ts():
    obj = {"a": {"b": [{"c": 5}]}}
    assert get_path(obj, "a.b.0.c") == 5 and get_path(obj, "a.x.c") is None
    assert parse_ts(1_700_000_000_000) == 1_700_000_000.0
    assert parse_ts("2026-01-01T00:00:00Z") is not None and parse_ts("nope") is None


def _write(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        for ln in lines:
            f.write(json.dumps(ln) + "\n")


def _jsonl(tmp_path, **opts):
    spec = AgentSpec("bot", "Bot", "#fff", "jsonl", options={
        "files": str(tmp_path / "logs" / "**" / "*.jsonl"), "match": {"type": "usage"},
        "tokens_in": "usage.in", "tokens_out": "usage.out", "cost": "usage.usd",
        "model": "model", "cwd": "cwd", **opts})
    return JsonlSource(spec, SourceContext())


def test_jsonl_sums_today_and_reads_incrementally(tmp_path):
    f = tmp_path / "logs" / "2026" / "sess-a.jsonl"
    _write(f, [{"type": "meta", "cwd": "/w/my-app", "model": "m1"},
               {"type": "usage", "usage": {"in": 100, "out": 10, "usd": 0.5}},
               {"type": "chat"}])
    src = _jsonl(tmp_path)
    st = src.stats()
    assert (st.tokens_in, st.tokens_out, st.cost_usd) == (100, 10, 0.5)
    assert st.sessions[0].label == "my-app" and st.sessions[0].id == "sess-a" and st.sessions[0].live
    _write(f, [{"type": "usage", "usage": {"in": 50, "out": 5, "usd": 0.25}}])
    st = src.stats()
    assert (st.tokens_in, st.cost_usd) == (150, 0.75)          # only the new line was added


def test_jsonl_running_totals_and_states(tmp_path):
    f = tmp_path / "logs" / "s.jsonl"
    _write(f, [{"type": "usage", "usage": {"in": 100}}, {"type": "usage", "usage": {"in": 180}},
               {"type": "approval"}])
    src = _jsonl(tmp_path, totals="last", waiting_when={"type": "approval"}, done_when={"type": "end"})
    st = src.stats()
    assert st.tokens_in == 180
    assert st.sessions[0].needs_input and st.sessions[0].attention_kind == "needs"
    _write(f, [{"type": "end"}])
    assert src.stats().sessions[0].attention_kind == "idle"


def test_jsonl_ignores_old_files(tmp_path):
    f = tmp_path / "logs" / "old.jsonl"
    _write(f, [{"type": "usage", "usage": {"in": 999}}])
    old = time.time() - 3 * 86400
    os.utime(f, (old, old))
    st = _jsonl(tmp_path).stats()
    assert st.tokens_in == 0 and st.sessions == []


def test_jsonl_requires_files():
    with pytest.raises(ValueError):
        JsonlSource(AgentSpec("x", "x", "#fff", "jsonl"), SourceContext())


def _otlp(service, metric, value, attrs, temporality=1):
    return {"resourceMetrics": [{
        "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": service}}]},
        "scopeMetrics": [{"metrics": [{"name": metric, "sum": {
            "aggregationTemporality": temporality,
            "dataPoints": [{"asDouble": value, "attributes": [
                {"key": k, "value": {"stringValue": v}} for k, v in attrs.items()]}]}}]}]}]}


def test_otel_matches_service_and_handles_temporality(tmp_path, monkeypatch):
    import code_deck.agents.otel as mod
    monkeypatch.setattr(mod.config, "STATE_DIR", tmp_path)
    recv = SimpleNamespace(listeners=[])
    ctx = SourceContext()
    ctx.shared["otel"] = recv
    spec = AgentSpec("g", "G", "#fff", "otel", options={
        "service": "gem", "cost_metric": "gem.cost", "tokens_metric": "gem.tokens"})
    src = OtelSource(spec, ctx)
    assert recv.listeners == [src.ingest]
    src.ingest(_otlp("gem", "gem.cost", 0.5, {"session.id": "s1", "cwd": "/x/proj"}))
    src.ingest(_otlp("gem", "gem.cost", 0.25, {"session.id": "s1"}))
    src.ingest(_otlp("other", "gem.cost", 9.0, {"session.id": "s1"}))           # not ours
    src.ingest(_otlp("gem", "gem.tokens", 100, {"session.id": "s1", "type": "input"}, temporality=2))
    src.ingest(_otlp("gem", "gem.tokens", 160, {"session.id": "s1", "type": "input"}, temporality=2))
    st = src.stats()
    assert st.cost_usd == 0.75 and st.tokens_in == 160
    assert st.sessions[0].label == "proj" and st.sessions[0].live
    again = OtelSource(spec, ctx).stats()                                       # persisted
    assert again.cost_usd == 0.75


def test_otel_needs_a_metric():
    ctx = SourceContext()
    ctx.shared["otel"] = SimpleNamespace(listeners=[])
    with pytest.raises(ValueError):
        OtelSource(AgentSpec("g", "G", "#fff", "otel", options={"service": "x"}), ctx)
