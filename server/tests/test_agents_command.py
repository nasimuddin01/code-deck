"""command source: runs a script, parses its JSON, isolates failures."""
import json
import sys
import time

import pytest

from code_deck.agents.command import CommandSource
from code_deck.agents.registry import SourceContext
from code_deck.agents.spec import AgentSpec


def _src(tmp_path, body: str, **opts):
    script = tmp_path / "agent.py"
    script.write_text(body)
    spec = AgentSpec("bot", "Bot", "#fff", "command",
                     options={"command": [sys.executable, str(script)], "interval": 3600, **opts})
    woke = []
    src = CommandSource(spec, SourceContext(wake=lambda: woke.append(1)))
    deadline = time.time() + 5
    while src._error == "not run yet" and time.time() < deadline:
        time.sleep(0.02)
    return src, woke


def test_reads_payload(tmp_path):
    out = {"cost_usd": 1.5, "quota_pct": 20, "sessions": [{"id": "s", "state": "working", "cwd": "/a/proj"}]}
    src, woke = _src(tmp_path, f"print({json.dumps(json.dumps(out))})")
    st = src.stats()
    src.close()
    assert st.cost_usd == 1.5 and st.quota_pct == 20 and st.sessions[0].label == "proj" and woke


def test_failure_raises_then_keeps_last_good(tmp_path):
    src, _ = _src(tmp_path, "import sys; sys.exit(3)")
    with pytest.raises(RuntimeError, match="exit 3"):
        src.stats()
    good = tmp_path / "agent.py"
    good.write_text("print('{\"cost_usd\": 2}')")
    src.run_once()
    assert src.stats().cost_usd == 2
    good.write_text("print('not json')")
    src.run_once()
    st = src.stats()
    src.close()
    assert st.cost_usd == 2 and st.note == "stale"


def test_timeout(tmp_path):
    src, _ = _src(tmp_path, "import time; time.sleep(5)", timeout=1)
    with pytest.raises(RuntimeError, match="timed out"):
        src.stats()
    src.close()


def test_needs_command():
    with pytest.raises(ValueError):
        CommandSource(AgentSpec("x", "x", "#fff", "command"), SourceContext())


def test_shell_string(tmp_path):
    spec = AgentSpec("sh", "Sh", "#fff", "command",
                     options={"command": "echo '{\"note\": \"hi\"}' | cat", "interval": 3600})
    src = CommandSource(spec, SourceContext())
    time.sleep(0.5)
    st = src.stats()
    src.close()
    assert st.note == "hi"
