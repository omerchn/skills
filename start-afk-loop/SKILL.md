---
name: start-afk-loop
description: Start the AFK agent loop. Runs /afk-loop-tick every 15 minutes via /loop. Run once per session.
user_invocable: true
allowed-tools: Skill
---

# Start AFK Loop

Start a session-scoped loop that invokes `/afk-loop-tick` every 15 minutes.

## Steps

Invoke the `loop` skill with args `15m /afk-loop-tick`.

The loop is session-scoped and will stop when this Claude Code session ends.
