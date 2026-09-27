"""Python plugins: your own source class, from a file or an installed package.

A local file, no packaging:

    [agents.my-agent]
    source = "python"
    file = "~/code-deck-agents/my_agent.py"   # or: module = "my_pkg.agents"
    class = "Source"                          # default "Source"; a function works too
    # any other keys reach your code as spec.options

    # ~/code-deck-agents/my_agent.py
    class Source:
        def __init__(self, spec, ctx):        # spec.options holds your agents.toml keys
            ...
        def stats(self):                      # called every tick (default 10 s)
            return {"cost_usd": 1.2, "sessions": [{"id": "a", "state": "working", "cwd": "/p/app"}]}
        def close(self):                      # optional
            ...

`stats()` may return a dict in the payload.py shape (easiest) or a
`code_deck.providers.stats.ToolStats`. Keep it fast: it runs on the stats
thread; do slow work in your own thread (see agents/command.py).

An installed package can also add a brand-new source *type* for everyone:

    # the plugin's pyproject.toml
    [project.entry-points."code_deck.sources"]
    gemini = "code_deck_gemini:GeminiSource"

after which `source = "gemini"` works in agents.toml. The built-in agents
(claude-code, claude-max, codex) are registered through this same mechanism.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys
from importlib.metadata import entry_points

from .registry import SourceContext, register_source
from .spec import AgentSpec

log = logging.getLogger(__name__)
ENTRY_POINT_GROUP = "code_deck.sources"


def _load_module(spec: AgentSpec):
    o = spec.options
    if o.get("file"):
        path = os.path.expanduser(str(o["file"]))
        if not os.path.isfile(path):
            raise FileNotFoundError(f"plugin file not found: {path}")
        name = f"code_deck_plugin_{spec.id.replace('-', '_')}"
        mspec = importlib.util.spec_from_file_location(name, path)
        if mspec is None or mspec.loader is None:
            raise ImportError(f"can't load {path}")
        mod = importlib.util.module_from_spec(mspec)
        sys.modules[name] = mod
        mspec.loader.exec_module(mod)
        return mod
    if o.get("module"):
        modname, _, attr = str(o["module"]).partition(":")
        mod = importlib.import_module(modname)
        if attr:
            o.setdefault("class", attr)
        return mod
    raise ValueError('python source needs `file = "path.py"` or `module = "pkg.mod"`')


def python_source(spec: AgentSpec, ctx: SourceContext):
    mod = _load_module(spec)
    attr = str(spec.options.get("class", "Source"))
    factory = getattr(mod, attr, None)
    if factory is None or not callable(factory):
        raise AttributeError(f"{attr!r} not found in the plugin (set `class = \"...\"`)")
    src = factory(spec, ctx)
    if not callable(getattr(src, "stats", None)):
        raise TypeError(f"{attr} must return an object with a stats() method")
    return src


register_source("python", python_source)


def load_entry_points() -> list[str]:
    """Register source types from installed packages. Returns their names."""
    names = []
    try:
        eps = entry_points(group=ENTRY_POINT_GROUP)
    except Exception as e:  # pragma: no cover - broken metadata
        log.warning("plugin discovery failed: %s", e)
        return names
    for ep in eps:
        try:
            register_source(ep.name, ep.load())
            names.append(ep.name)
        except Exception as e:
            log.warning("plugin source %r (%s) failed to load: %s", ep.name, ep.value, e)
    return names
