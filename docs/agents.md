# Adding your own coding agents

CODE DECK ships with three agents: **Claude Code**, **Claude Max** and
**Codex**. You can add any other agent or harness, or hide and rename the
built-ins, in one file:

```
~/.config/code-deck/agents.toml        (or set CODE_DECK_AGENTS_FILE)
```

Every agent gets a colour, an account card you can place in the builder, and
rows in the session list. A session reported as waiting also plays the
needs-you banner and triggers the menu bar notification, the same as Claude
Code.

Copy [`examples/agents/agents.toml`](../examples/agents/agents.toml) to get
started, then restart:

```sh
code-deck service restart
code-deck agents list          # shows every agent, its source, and any error
```

## Choosing a source

| Your agent… | Use | Effort |
|---|---|---|
| can run a shell command on its events (hooks) | `push` | a few hook lines |
| has usage you can fetch with a script | `command` | one script |
| writes one JSON-lines log file per session | `jsonl` | field mapping only |
| exports OpenTelemetry metrics | `otel` | point its exporter at us |
| needs something custom | `python` | one class |

## Built-ins: rename or hide

```toml
[agents.claude-max]
enabled = false

[agents.claude-code]
name = "Claude"
color = "#ff7a45"      # hex, or a theme name: orange violet blue good warning critical attention
```

## Session states

Every custom source reports sessions in the same four states:

| State | Row shows | Also |
|---|---|---|
| `working` | green **live** | goes grey after two minutes without an update |
| `waiting` | blue **needs you** | plays the banner and posts a menu bar notification |
| `done` | blue **turn ended** | menu bar notification |
| `idle` | grey, time since last activity | |

A session with no news for 20 minutes drops off the list. The row is named
after the session's folder (`cwd`) unless you send a `label`.

## `push`: the agent reports its own status

```toml
[agents.my-agent]
name = "My Agent"
source = "push"
```

From a hook or script:

```sh
code-deck push my-agent "$SESSION_ID" --state working
code-deck push my-agent "$SESSION_ID" --state waiting   # needs you
code-deck push my-agent "$SESSION_ID" --state done      # turn ended
code-deck push my-agent "$SESSION_ID" --end             # session closed
code-deck push my-agent --cost 3.20 --quota 41          # agent-level totals
```

Add `-q` inside hooks, so a stopped dashboard never fails your agent. The
row name defaults to the current folder. You don't even need the
`agents.toml` entry: pushing to a new id creates the agent with an automatic
colour. Declare it only to set its name and colour.

Without the CLI it's plain HTTP on the dashboard's port:

```
POST   /api/agents/<agent>                        agent totals, optional "sessions": [...]
POST   /api/agents/<agent>/sessions/<session>     one session
DELETE /api/agents/<agent>/sessions/<session>     session finished
```

```sh
curl -X POST http://127.0.0.1:8765/api/agents/my-agent/sessions/abc \
     -H 'content-type: application/json' \
     -d '{"state": "waiting", "cwd": "/Users/me/code/my-app", "model": "gpt-5"}'
```

Pushed state survives a restart. Built-in agents refuse pushes.

## `command`: run a script, read its JSON

```toml
[agents.usage]
name = "Usage"
source = "command"
command = "python3 ~/code-deck-agents/usage.py"   # a string runs through /bin/sh; a list runs directly
interval = 60                                      # seconds, min 2, default 30
timeout = 10
```

The script prints one JSON object in the [payload shape](#the-payload-shape)
and exits 0. See [`examples/agents/usage.py`](../examples/agents/usage.py).
If a run fails, the card shows **error**, or **stale** while it keeps the
last good numbers. `code-deck agents list` shows the reason.

## `jsonl`: read the agent's own logs

```toml
[agents.my-cli]
name = "My CLI"
source = "jsonl"
files = "~/.my-cli/sessions/**/*.jsonl"   # glob; ** recurses
session = "file"                           # "file" name, "dir" name, or a field path
match = { type = "usage" }                 # only count matching lines (optional)
timestamp = "timestamp"                    # ISO-8601 or epoch; default: file mtime
model = "model"
cwd = "cwd"
tokens_in = "usage.input_tokens"           # dot paths; list items by index: "choices.0.usage"
tokens_out = "usage.output_tokens"
cost = "usage.cost_usd"
totals = "sum"                             # "sum": lines are deltas · "last": lines carry running totals
waiting_when = { type = "approval_request" }   # optional
done_when = { type = "turn_complete" }         # optional
```

Only today's lines count, in local time. A file written in the last two
minutes is a live session. Files are read incrementally.

Get `totals` right, or the numbers will be wrong. If each line holds the
usage for that one request, use `"sum"`. If each line holds the session's
total so far, as Codex does, use `"last"`.

## `otel`: OpenTelemetry metrics

Point the agent's OTLP/HTTP **JSON** metrics exporter at
`http://127.0.0.1:4318` (`CODE_DECK_OTLP_PORT`). That's the same receiver
Claude Code uses.

```toml
[agents.my-otel-agent]
name = "OTel Agent"
source = "otel"
service = "my-agent"                  # resource attribute service.name
cost_metric = "my_agent.cost.usage"   # USD (optional)
tokens_metric = "my_agent.token.usage"
token_type_attr = "type"              # attribute valued "input" / "output"
session_attr = "session.id"
model_attr = "model"
cwd_attr = "cwd"
```

Delta and cumulative counters are both handled, and today's totals survive
a restart.

## `python`: your own class

```toml
[agents.custom]
source = "python"
file = "~/code-deck-agents/my_agent.py"    # or module = "my_pkg.agents:Source"
class = "Source"                           # default; a function works too
project = "anything else"                  # extra keys arrive as spec.options
```

```python
class Source:
    def __init__(self, spec, ctx):
        self.project = spec.options.get("project")

    def stats(self):                        # every tick (default 10 s): keep it fast
        return {"cost_usd": 1.2,
                "sessions": [{"id": "a", "state": "working", "cwd": "/Users/me/code/app"}]}
```

`stats()` returns a dict in the payload shape, or a `ToolStats`. Do slow
work in your own thread.

**Packaging a source for others.** An installed package can register a new
source type for everyone:

```toml
# the plugin's pyproject.toml
[project.entry-points."code_deck.sources"]
gemini = "code_deck_gemini:GeminiSource"
```

After `pipx inject code-deck code-deck-gemini`, `source = "gemini"` works in
anyone's `agents.toml`. The built-in agents register through this same
mechanism.

## The payload shape

Used by `push` bodies, `command` output and `python` return values. Every
field is optional except a session's `id`.

```jsonc
{
  "model": "gpt-5",
  "cost_usd": 3.20,              // today's spend; default: sum of sessions
  "tokens_in": 120000,           // today's totals; default: sum of sessions
  "tokens_out": 9000,
  "sessions_today": 4,           // default: number of sessions
  "quota_pct": 42,               // share of the plan used, 0-100
  "quota_resets_at": 1790000000, // epoch seconds
  "note": "paused",              // short text when there's no number to show
  "activity_24h": [0, 1, 3],     // up to 24 hourly buckets for the sparkline
  "sessions": [
    {"id": "abc", "label": "my-app", "cwd": "/Users/me/code/my-app", "model": "gpt-5",
     "state": "working", "tokens_in": 1000, "tokens_out": 200, "cost_usd": 0.12,
     "last_active": 1790000000}
  ]
}
```

Numbers are **running totals, not deltas**: send the latest value each time.

## Showing an agent on the screen

Open the builder, drag an **Account card** onto the screen, and pick your
agent in the inspector. **auto** shows quota when the agent reports one and
spend otherwise. The **Session list** shows every agent unless you limit it.

## How accurate are the numbers?

A card is only as accurate as its source. The built-ins use each tool's own
records:

| Agent | Where the number comes from | Accuracy |
|---|---|---|
| Claude Code spend | Claude Code's own cost telemetry (`claude_code.cost.usage`) | Exact once telemetry is on: the same figure Claude Code computes. Before that it's an estimate from transcript tokens and list prices, marked `est`. For a session that ran partly before telemetry, the larger of the two is shown, so the day's total never drops. |
| Codex quota | The Codex app-server's rate-limit data | The same weekly percentage and reset time the Codex app shows. Without the app-server, it's the latest value Codex wrote to its session files. |
| Claude Max quota | No local source yet | Shows a status note rather than guessing. |
| Sessions, needs you, turn ended | Claude Code transcripts and hooks; Codex session files | Picked up on the next refresh, every 10 s by default (Settings in the builder). Pushed updates show immediately. |

Custom agents show exactly what their source reports. A quota appears only
if the agent provides one; CODE DECK never invents a percentage. For
`jsonl`, choosing `totals` correctly matters most.
