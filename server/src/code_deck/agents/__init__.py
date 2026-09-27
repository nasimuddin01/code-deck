"""Pluggable coding agents.

An *agent* is one card's worth of data: a name, a colour, today's totals and a
list of sessions (the wire type is still `ToolStats`, for compatibility). Each
agent gets its data from a *source*:

  claude-code / claude-max / codex   the built-ins (transcripts, telemetry, app-server)
  push      anything POSTs its status to /api/agents/<id>/... (or `code-deck push`)
  command   CODE DECK runs a script every N seconds and reads its JSON output
  jsonl     per-session log files, mapped with a few field paths
  otel      OpenTelemetry metrics sent to the built-in receiver, matched by service.name
  python    your own class, from a file or an installed package (entry points)

Agents are declared in ~/.config/code-deck/agents.toml (CODE_DECK_AGENTS_FILE);
see docs/agents.md.
"""
from ..providers.stats import SessionInfo, ToolStats
from .payload import session_from, stats_from
from .registry import AgentRegistry, SourceContext, register_source
from .spec import AgentSpec, load_specs

# the plugin-facing API: everything a source needs
__all__ = ["AgentRegistry", "AgentSpec", "SessionInfo", "SourceContext", "ToolStats",
           "load_specs", "register_source", "session_from", "stats_from"]
