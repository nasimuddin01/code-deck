#!/usr/bin/env bash
# Example: drive a push agent from any tool that can run shell hooks.
# Wire these three lines into your agent's lifecycle hooks (names vary by tool):
#
#   on session/turn start:   code-deck push my-agent "$SESSION_ID" --state working -q
#   on approval/question:    code-deck push my-agent "$SESSION_ID" --state waiting -q
#   on turn finished:        code-deck push my-agent "$SESSION_ID" --state done -q
#   on session exit:         code-deck push my-agent "$SESSION_ID" --end -q
#
# -q never fails or prints, so a stopped dashboard can't break your agent.
# Without the CLI, plain HTTP works the same:
#
#   curl -s -X POST http://127.0.0.1:8765/api/agents/my-agent/sessions/$SESSION_ID \
#        -H 'content-type: application/json' \
#        -d '{"state": "waiting", "cwd": "'"$PWD"'"}'
set -euo pipefail
SESSION_ID="${SESSION_ID:-demo-$$}"
code-deck push my-agent "$SESSION_ID" --state working
sleep 3
code-deck push my-agent "$SESSION_ID" --state waiting
sleep 3
code-deck push my-agent "$SESSION_ID" --end
