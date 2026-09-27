#!/usr/bin/env python3
"""Example `command` source: print one JSON object and exit 0.

Replace the body with however your agent exposes usage: an API call, a
CLI's `--json` output, a local database. CODE DECK runs this every
`interval` seconds (agents.toml) and shows the result.
"""
import json
import os
import time

print(json.dumps({
    "model": "example-model",
    "cost_usd": 1.84,                 # today's spend
    "quota_pct": 37,                  # share of the plan used (omit if none)
    "quota_resets_at": time.time() + 3 * 86400,
    "sessions": [
        {"id": "demo-1", "cwd": os.path.expanduser("~/code/my-app"), "state": "working",
         "tokens_in": 120_000, "tokens_out": 8_000},
        {"id": "demo-2", "cwd": os.path.expanduser("~/code/api"), "state": "waiting"},
    ],
}))
