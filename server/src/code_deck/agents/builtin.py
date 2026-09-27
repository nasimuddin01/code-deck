"""The three built-in agents, registered as ordinary sources."""
from __future__ import annotations

from ..providers.live import ClaudeCodeLiveProvider, ClaudeMaxProvider, CodexLiveProvider
from ..providers.otel_receiver import OtelReceiver
from .registry import SourceContext, register_source
from .spec import AgentSpec


def otel_receiver(ctx: SourceContext) -> OtelReceiver | None:
    """The shared in-process OTLP receiver (Claude Code telemetry and `otel`
    agents). Best-effort: if the port is taken, cost falls back to estimates."""
    def make():
        try:
            return OtelReceiver().start()
        except OSError:
            return None
    return ctx.service("otel", make)


class _Wrap:
    def __init__(self, provider) -> None:
        self.p = provider

    def stats(self):
        return self.p.stats()


register_source("claude-code", lambda spec, ctx: _Wrap(ClaudeCodeLiveProvider(otel=otel_receiver(ctx))))
register_source("claude-max", lambda spec, ctx: _Wrap(ClaudeMaxProvider()))
register_source("codex", lambda spec, ctx: _Wrap(CodexLiveProvider()))

__all__ = ["AgentSpec", "otel_receiver"]
