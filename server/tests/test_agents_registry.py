"""agents.toml parsing and the registry (built-ins stay on, custom agents
added, failures isolated per agent)."""
from code_deck.agents.registry import AgentRegistry, register_source
from code_deck.agents.spec import load_specs, parse_specs
from code_deck.providers.stats import ToolStats


def _ids(specs):
    return [s.id for s in specs]


def test_builtins_without_a_file(tmp_path):
    specs, errors = load_specs(tmp_path / "missing.toml")
    assert _ids(specs) == ["claude-code", "claude-max", "codex"]
    assert errors == []


def test_disable_rename_and_add():
    errors = []
    specs = parse_specs({"agents": {
        "codex": {"enabled": False},
        "claude-code": {"name": "Claude", "color": "#ff0000"},
        "aider": {"source": "push", "name": "Aider"},
        "gemini": {"source": "push"},
    }}, errors)
    by = {s.id: s for s in specs}
    assert errors == []
    assert by["codex"].enabled is False
    assert by["claude-code"].name == "Claude" and by["claude-code"].color == "#ff0000"
    assert by["aider"].name == "Aider" and by["aider"].color.startswith("#")
    assert by["gemini"].name == "gemini"
    assert by["aider"].color != by["gemini"].color


def test_invalid_entries_are_reported_not_fatal():
    errors = []
    specs = parse_specs({"agents": {"Bad Id": {"source": "push"}, "nosrc": {"name": "x"},
                                    "codex": {"source": "push"}}}, errors)
    assert "nosrc" not in _ids(specs)
    assert len(errors) == 3


def test_bad_toml_keeps_builtins(tmp_path):
    f = tmp_path / "agents.toml"
    f.write_text("[agents.x\nsource=")
    specs, errors = load_specs(f)
    assert _ids(specs) == ["claude-code", "claude-max", "codex"] and errors


class _Fixed:
    def __init__(self, spec, ctx):
        self.spec = spec

    def stats(self):
        return ToolStats(name="ignored", model="m", sessions_today=1, tokens_in=10,
                         tokens_out=2, cost_usd=0.5)


class _Broken:
    def __init__(self, spec, ctx):
        pass

    def stats(self):
        raise RuntimeError("boom")


def test_registry_stamps_identity_and_isolates_failures():
    register_source("test-fixed", _Fixed)
    register_source("test-broken", _Broken)
    specs = parse_specs({"agents": {
        "claude-code": {"enabled": False}, "claude-max": {"enabled": False}, "codex": {"enabled": False},
        "a": {"source": "test-fixed", "name": "Agent A", "color": "#123456"},
        "b": {"source": "test-broken"},
        "c": {"source": "does-not-exist"},
    }})
    reg = AgentRegistry(specs)
    stats = {s.agent_id: s for s in reg.get_stats()}
    assert set(stats) == {"a", "b", "c"}
    assert stats["a"].name == "Agent A" and stats["a"].color == "#123456" and stats["a"].cost_usd == 0.5
    assert stats["b"].note == "error" and stats["c"].note == "error"
    meta = {a["id"]: a for a in reg.agents()}
    assert "boom" in meta["b"]["error"] and "unknown source" in meta["c"]["error"]


def test_ensure_agent_creates_dynamic_push_agent():
    reg = AgentRegistry(parse_specs({"agents": {
        "claude-code": {"enabled": False}, "claude-max": {"enabled": False}, "codex": {"enabled": False}}}))
    s = reg.ensure_agent("my-bot")
    assert s.dynamic and s.source == "push" and reg.ensure_agent("my-bot") is s
