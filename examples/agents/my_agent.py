"""Example `python` source (agents.toml: source = "python", file = "<this file>").

stats() runs every tick on the stats thread, so keep it fast. Return a dict
in the payload shape (docs/agents.md), or a ToolStats.
"""
import time


class Source:
    def __init__(self, spec, ctx):
        # spec.options has every extra key from this agent's agents.toml table
        self.started = time.time()
        self.project = spec.options.get("project", "my-project")

    def stats(self):
        minutes = int((time.time() - self.started) / 60)
        return {
            "note": f"up {minutes}m",
            "sessions": [{"id": "main", "label": self.project, "state": "working"}],
        }

    def close(self):
        pass
