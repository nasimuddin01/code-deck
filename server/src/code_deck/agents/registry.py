"""Turn agent specs into live sources and collect their stats every tick.

A *source factory* is `factory(spec, ctx) -> source`, where a source has
`stats() -> ToolStats` and optionally `close()`. The built-ins register here
exactly the way a plugin does, via `register_source()`.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..providers.stats import ToolStats
from .spec import AgentSpec, auto_color

log = logging.getLogger(__name__)


class AgentSource(Protocol):
    def stats(self) -> ToolStats: ...


SourceFactory = Callable[[AgentSpec, "SourceContext"], AgentSource]
_SOURCES: dict[str, SourceFactory] = {}


def register_source(name: str, factory: SourceFactory) -> None:
    """Make `source = "<name>"` available in agents.toml."""
    _SOURCES[name] = factory


def source_names() -> list[str]:
    _ensure_builtins()
    return sorted(_SOURCES)


@dataclass
class SourceContext:
    """Shared services handed to every source factory."""
    wake: Callable[[], None] = lambda: None          # ask the sampler for an immediate tick
    shared: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def service(self, key: str, make: Callable[[], Any]) -> Any:
        """One instance per key, created on first use (e.g. the OTLP receiver)."""
        with self._lock:
            if key not in self.shared:
                self.shared[key] = make()
            return self.shared[key]


def empty_stats(spec: AgentSpec, note: str = "") -> ToolStats:
    return ToolStats(name=spec.name, model="", sessions_today=0, tokens_in=0, tokens_out=0,
                     cost_usd=0.0, live=False, note=note)


class AgentRegistry:
    def __init__(self, specs: list[AgentSpec], ctx: SourceContext | None = None,
                 errors: list[str] | None = None) -> None:
        _ensure_builtins()
        self.ctx = ctx or SourceContext()
        self.errors: list[str] = list(errors or [])
        self._lock = threading.Lock()
        self._specs: list[AgentSpec] = []
        self._sources: dict[str, AgentSource | None] = {}
        self._agent_errors: dict[str, str] = {}
        for s in specs:
            self._add(s)

    # -- setup ----------------------------------------------------------------
    def _add(self, spec: AgentSpec) -> None:
        self._specs.append(spec)
        if not spec.enabled:
            return
        factory = _SOURCES.get(spec.source)
        if factory is None:
            msg = f"unknown source {spec.source!r} (have: {', '.join(sorted(_SOURCES))})"
            self._agent_errors[spec.id] = msg
            self.errors.append(f"[agents.{spec.id}] {msg}")
            self._sources[spec.id] = None
            return
        try:
            self._sources[spec.id] = factory(spec, self.ctx)
        except Exception as e:   # bad options must not take down the other agents
            log.warning("agent %s: %s", spec.id, e)
            self._agent_errors[spec.id] = str(e)
            self.errors.append(f"[agents.{spec.id}] {e}")
            self._sources[spec.id] = None

    def spec(self, agent_id: str) -> AgentSpec | None:
        return next((s for s in self._specs if s.id == agent_id), None)

    def ensure_agent(self, agent_id: str, source: str = "push") -> AgentSpec:
        """An agent for this id, created on the fly if nobody declared it
        (so `code-deck push my-agent ...` works with zero config)."""
        with self._lock:
            s = self.spec(agent_id)
            if s is None:
                custom = sum(1 for x in self._specs if not x.builtin)
                s = AgentSpec(agent_id, agent_id, auto_color(custom), source, dynamic=True)
                self._add(s)
            return s

    # -- per tick -------------------------------------------------------------
    def get_stats(self) -> list[ToolStats]:
        out = []
        with self._lock:
            items = [(s, self._sources.get(s.id)) for s in self._specs if s.enabled]
        for spec, src in items:
            if src is None:
                st = empty_stats(spec, "error")
            else:
                try:
                    st = src.stats()
                    self._agent_errors.pop(spec.id, None)
                except Exception as e:
                    log.warning("agent %s stats failed: %s", spec.id, e)
                    self._agent_errors[spec.id] = str(e)
                    st = empty_stats(spec, "error")
            st.name, st.agent_id, st.color, st.source = spec.name, spec.id, spec.color, spec.source
            out.append(st)
        return out

    def agents(self) -> list[dict]:
        with self._lock:
            return [{**s.public(), "error": self._agent_errors.get(s.id, "")} for s in self._specs]

    def close(self) -> None:
        for src in self._sources.values():
            close = getattr(src, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass


# -- built-in sources ------------------------------------------------------------

_builtins_done = False


def _ensure_builtins() -> None:
    global _builtins_done
    if _builtins_done:
        return
    _builtins_done = True
    from . import (  # noqa: F401  (each module registers its source types)
        builtin,
        command,
        jsonl,
        otel,
        push,
    )
