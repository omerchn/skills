---
name: start-afk-loop
description: Start the AFK agent loop cron job. Creates a session-scoped cron that invokes /afk-loop-tick every 15 minutes. Run once per session.
user_invocable: true
allowed-tools: CronCreate, CronList
---

# Start AFK Loop

Start a session-scoped cron job that invokes `/afk-loop-tick` every 15 minutes.

## Steps

### 1. Check for Existing Cron

Before creating a new cron, check if an AFK loop cron is already running using `CronList`. If one exists with a prompt containing "afk-loop-tick", tell the user it's already active and report the job ID. Skip creation.

### 2. Create the Cron Job

Use `CronCreate` with:
- `cron`: `"*/15 * * * *"`
- `recurring`: `true`
- `prompt`: `/afk-loop-tick`

Report the job ID to the user so they can cancel it later if needed. Remind them this cron is session-scoped and will stop when this Claude Code session ends.
