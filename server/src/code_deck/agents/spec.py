"""Agent declarations: the built-ins plus whatever agents.toml adds.

    # ~/.config/code-deck/agents.toml
    [agents.codex]
    enabled = false                 # hide a built-in

    [agents.aider]
    name = "Aider"                  # shown on cards and rows
    color = "#4ade80"               # hex or a theme name: orange violet blue good warning critical
    source = "push"                 # push | command | jsonl | otel | python
    # ...source-specific keys (see docs/agents.md)
"""
from __future__ import annotations

import logging
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import config

log = logging.getLogger(__name__)

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
# auto colours for agents that don't pick one (after the built-ins' orange/violet/blue)
AUTO_COLORS = ("#4ade80", "#f472b6", "#facc15", "#2dd4bf", "#f87171", "#a3e635", "#38bdf8", "#fb923c")
RESERVED_KEYS = {"name", "color", "source", "enabled"}


@dataclass
class AgentSpec:
    id: str
    name: str
    color: str
    source: str
    enabled: bool = True
    builtin: bool = False
    options: dict[str, Any] = field(default_factory=dict)   # source-specific settings
    dynamic: bool = False       # created on the fly by a push to an unknown id

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "color": self.color, "source": self.source,
                "enabled": self.enabled, "builtin": self.builtin, "dynamic": self.dynamic}


def builtin_specs() -> list[AgentSpec]:
    return [
        AgentSpec("claude-code", "Claude Code", "orange", "claude-code", builtin=True),
        AgentSpec("claude-max", "Claude Max", "violet", "claude-max", builtin=True),
        AgentSpec("codex", "Codex", "blue", "codex", builtin=True),
    ]


def auto_color(index: int) -> str:
    return AUTO_COLORS[index % len(AUTO_COLORS)]


def parse_specs(data: dict, errors: list[str] | None = None) -> list[AgentSpec]:
    """Built-ins, overlaid with the `[agents.<id>]` tables in `data`."""
    errors = errors if errors is not None else []
    specs = {s.id: s for s in builtin_specs()}
    table = data.get("agents", {})
    if not isinstance(table, dict):
        errors.append("`agents` must be a table: [agents.<id>]")
        return list(specs.values())
    custom = 0
    for aid, raw in table.items():
        if not ID_RE.match(str(aid)):
            errors.append(f"agent id {aid!r}: use lowercase letters, digits, - or _ (max 32)")
            continue
        if not isinstance(raw, dict):
            errors.append(f"[agents.{aid}] must be a table")
            continue
        opts = {k: v for k, v in raw.items() if k not in RESERVED_KEYS}
        if aid in specs:                       # tweak a built-in
            s = specs[aid]
            s.name = str(raw.get("name", s.name))
            s.color = str(raw.get("color", s.color))
            s.enabled = bool(raw.get("enabled", True))
            if "source" in raw and raw["source"] != s.source:
                errors.append(f"[agents.{aid}] is built in; its source can't be changed "
                              f"(pick another id for a custom agent)")
            s.options.update(opts)
            continue
        source = raw.get("source")
        if not source:
            errors.append(f"[agents.{aid}] needs a `source` (push | command | jsonl | otel | python)")
            continue
        specs[aid] = AgentSpec(
            id=aid, name=str(raw.get("name", aid)),
            color=str(raw.get("color") or auto_color(custom)),
            source=str(source), enabled=bool(raw.get("enabled", True)), options=opts)
        custom += 1
    return list(specs.values())


def load_specs(path: Path | None = None) -> tuple[list[AgentSpec], list[str]]:
    """(specs, errors). A missing file is fine: just the built-ins."""
    path = path or config.AGENTS_FILE
    errors: list[str] = []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {}
    except (OSError, tomllib.TOMLDecodeError) as e:
        errors.append(f"{path}: {e}")
        data = {}
    specs = parse_specs(data, errors)
    for e in errors:
        log.warning("agents.toml: %s", e)
    return specs, errors
