#!/usr/bin/env python3
"""Claude Code hook: mark a session as 'needs the user'.

Wired into ~/.claude/settings.json hooks. Claude Code invokes it with a JSON
event on stdin. We translate that into a per-session flag file the dashboard
reads to draw a blue "needs input" dot:

  Notification      -> Claude wants permission / has been waiting  -> set flag
  UserPromptSubmit  -> the user just responded                     -> clear flag
  SessionEnd        -> the session closed                          -> clear flag

Flags live in <CODE_DECK_CLAUDE_DIR, default ~/.claude>/code-deck/attention/<session_id>.json. Pure stdlib,
never blocks, always exits 0 — a hook failure must never disrupt a session.
"""
import json
import os
import sys
import time

from code_deck.config import ATTENTION_DIR

FLAG_DIR = str(ATTENTION_DIR)


def main() -> None:
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return
    sid = ev.get("session_id")
    if not sid:
        return
    event = ev.get("hook_event_name", "")
    path = os.path.join(FLAG_DIR, f"{sid}.json")

    if event in ("Notification", "Stop"):
        if event == "Stop":
            # Main agent finished its turn -> waiting on the user. Fires once per
            # turn, focus-independent (unlike the idle Notification, which only
            # fires when you've stepped away). Soft "turn ended", no overlay.
            msg, kind = "turn ended", "idle"
        else:
            msg = ev.get("message", "")
            # Notification fires on permission prompts, questions, AND (only when
            # you've stepped away) ~60s idle. The idle wording is a soft "turn
            # ended"; everything else is really blocked on you. Default "needs"
            # so an unrecognized message stays the louder label.
            kind = "idle" if "waiting for your input" in msg.lower() else "needs"
        try:
            os.makedirs(FLAG_DIR, exist_ok=True)
            with open(path, "w") as f:
                json.dump({"cwd": ev.get("cwd", ""), "ts": time.time(),
                           "message": msg, "kind": kind}, f)
        except OSError:
            pass
    else:  # UserPromptSubmit, SessionEnd -> user engaged / session gone
        try:
            os.remove(path)
        except OSError:
            pass


def run() -> None:
    """Console-script entry (`code-deck-hook`). A hook failure must never
    disrupt the calling Claude Code session, so this always exits 0."""
    try:
        main()
    except Exception:
        pass
    finally:
        sys.exit(0)


if __name__ == "__main__":
    run()
