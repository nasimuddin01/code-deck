"""python plugins: file and module loading, dict returns, entry points."""
import sys
from types import SimpleNamespace

from code_deck.agents import python as plugmod
from code_deck.agents.registry import _SOURCES, AgentRegistry
from code_deck.agents.spec import parse_specs

NO_BUILTINS = {"claude-code": {"enabled": False}, "claude-max": {"enabled": False},
               "codex": {"enabled": False}}
PLUGIN = '''
class Source:
    def __init__(self, spec, ctx):
        self.greeting = spec.options.get("greeting", "hi")
    def stats(self):
        return {"cost_usd": 2.0, "note": self.greeting,
                "sessions": [{"id": "p1", "state": "waiting", "cwd": "/w/plugged"}]}

def make(spec, ctx):
    return Source(spec, ctx)
'''


def _stats(agents):
    reg = AgentRegistry(parse_specs({"agents": {**NO_BUILTINS, **agents}}))
    return reg, {t.agent_id: t for t in reg.get_stats()}


def test_file_plugin_with_options_and_dict_return(tmp_path):
    f = tmp_path / "my_agent.py"
    f.write_text(PLUGIN)
    _, st = _stats({"mine": {"source": "python", "file": str(f), "greeting": "yo", "name": "Mine"}})
    t = st["mine"]
    assert t.name == "Mine" and t.cost_usd == 2.0 and t.note == "yo"
    assert t.sessions[0].label == "plugged" and t.sessions[0].attention_kind == "needs"


def test_module_plugin_with_function_factory(tmp_path, monkeypatch):
    (tmp_path / "deck_plug.py").write_text(PLUGIN)
    monkeypatch.syspath_prepend(str(tmp_path))
    _, st = _stats({"m": {"source": "python", "module": "deck_plug:make"}})
    assert st["m"].cost_usd == 2.0
    sys.modules.pop("deck_plug", None)


def test_bad_plugins_are_isolated(tmp_path):
    reg, st = _stats({"nofile": {"source": "python", "file": str(tmp_path / "missing.py")},
                      "noclass": {"source": "python", "file": __file__, "class": "Nope"}})
    assert st["nofile"].note == "error" and st["noclass"].note == "error"
    errs = {a["id"]: a["error"] for a in reg.agents()}
    assert "not found" in errs["nofile"] and "Nope" in errs["noclass"]


def test_entry_points_register_new_source_types(monkeypatch):
    class Fake:
        def __init__(self, spec, ctx):
            pass

        def stats(self):
            return {"note": "from a package"}

    ep = SimpleNamespace(name="fancy", value="pkg:Fake", load=lambda: Fake)
    monkeypatch.setattr(plugmod, "entry_points", lambda group: [ep] if group == "code_deck.sources" else [])
    assert plugmod.load_entry_points() == ["fancy"]
    _, st = _stats({"f": {"source": "fancy"}})
    assert st["f"].note == "from a package"
    _SOURCES.pop("fancy", None)


def test_builtins_are_registered_sources():
    from code_deck.agents.registry import source_names
    names = source_names()
    for n in ("claude-code", "claude-max", "codex", "push", "command", "jsonl", "otel", "python"):
        assert n in names
