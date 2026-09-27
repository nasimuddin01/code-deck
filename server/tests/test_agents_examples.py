"""The shipped examples in examples/agents/ must keep working."""
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from code_deck.agents.payload import stats_from
from code_deck.agents.registry import AgentRegistry
from code_deck.agents.spec import parse_specs

EX = Path(__file__).resolve().parents[2] / "examples" / "agents"


def test_example_agents_toml_parses_with_every_block_enabled():
    text = (EX / "agents.toml").read_text()
    # uncomment "# key = value" / "# [agents.x]" lines to check the commented recipes too
    enabled = re.sub(r"^# (\[agents\.[^\]]+\]|[a-z_]+ = .*)$", r"\1", text, flags=re.M)
    errors = []
    specs = parse_specs(tomllib.loads(enabled), errors)
    assert errors == []
    sources = {s.source for s in specs}
    assert {"push", "command", "jsonl", "otel", "python"} <= sources


def test_usage_script_output_is_a_valid_payload():
    out = subprocess.run([sys.executable, str(EX / "usage.py")], capture_output=True, text=True, check=True)
    st = stats_from("Usage", json.loads(out.stdout))
    assert st.quota_pct == 37 and len(st.sessions) == 2


def test_python_example_loads():
    reg = AgentRegistry(parse_specs({"agents": {
        "claude-code": {"enabled": False}, "claude-max": {"enabled": False}, "codex": {"enabled": False},
        "custom": {"source": "python", "file": str(EX / "my_agent.py"), "project": "demo"}}}))
    t = reg.get_stats()[0]
    assert t.note.startswith("up ") and t.sessions[0].label == "demo"
