# Changing the board

`SKILL.md` is what the skill does at run time. This file covers how to change the board's
code. Keep both in step: a new button means changes in the page, the server, the test and
`SKILL.md`.

## The three parts and their contract

```
session (Claude) ──writes──▶ <run>/board/board-state.json ──GET /state (2 s poll)──▶ index.html
session ◀──waits on── <run>/board/decisions.jsonl ◀──POST /decision── index.html (button click)
```

| File | Role |
|---|---|
| `board/index.html` | The whole UI. One file with no build step: vanilla JS plus `marked` and `DOMPurify` from cdnjs. It renders `board-state.json` and POSTs decisions. It holds no state of its own beyond what the user is choosing right now. |
| `board/server.py` | Stdlib server. Serves the page, `/state` (the state file verbatim), `/decided` and `/decision`. It validates and appends decisions and nothing more. It never edits state. |
| `board/test_server.py` | `python3 board/test_server.py` prints `ok`. Run it after any server change. |
| `board/example-state.json` | The state shape, with every field the page reads. Update it when you add a field. |
| `SKILL.md` | The decision table (what the session does for each `action`), the state fields, the run home and resume steps. |

Run data does **not** live here. It lives in `~/.claude/orchestrate-my-tickets/runs/<run>/`:
`run.json`, `board/` and that run's own `build_state.py` and `sync.sh`. Those two are
per-run scripts written during the run, so a change to them affects that run only.

## Rules that are easy to break

- **Security.** Bind to `127.0.0.1` only. Every endpoint checks the token: `?t=` for the
  page and the `X-Board-Token` header for the rest. Any site open in the browser can POST to
  localhost, so the token is the whole defence. Keep `server.json` at mode 600, and never
  log or print the token.
- **Decisions are an allow-list.** `ACTIONS` in `server.py` lists them; `NO_TICKET` lists the
  ones that may come without a `ticket`. Anything else gets a 400.
- **The page never assumes a write happened.** A click marks the item "sent" (`sent`,
  `deskSent`, `dispatched`). It disappears only when the session removes it from the state.
  `/decided` rebuilds those sets after a reload, so if a new action should survive a reload,
  teach `/decided` about it.
- **The drawer must not wipe input.** `renderDrawer` skips re-rendering while the user is
  typing (`drawerDirty`) and when nothing changed (`drawerRaw`). New inputs inside the drawer
  must set `drawerDirty` on input, or a 2-second poll erases them.
- **Escape everything.** Plain text goes through `esc()`. Markdown goes through `md()`, which
  is `marked` and then `DOMPurify`. Never put state text into `innerHTML` raw: it is
  agent-written and may quote PR or Jira content.
- **Pinned CDN versions only**, from cdnjs. No npm and no build step.
- **Restart-safe.** The server reads the state file on every request and keeps no memory, so
  restarting it is always safe. `server.json` keeps the URL stable across restarts.

## Recipes

**Add a button or action**
1. `index.html`: the button, and a handler that calls `post({action: "...", ...})`, then
   marks the item sent.
2. `server.py`: add it to `ACTIONS`, and to `NO_TICKET` if it has no ticket. If it should
   stay "sent" across a reload, add it to `/decided`.
3. `test_server.py`: assert the action is accepted (200), and extend the `/decided` assertion
   if you changed it.
4. `SKILL.md`: add a row to the decision table saying exactly what the session does, and
   what it must not do.

**Add a field to a card**: render it in `card()` (the board) and/or `renderDrawer()` (the
detail panel). Add it to `example-state.json`, and to the state field list in `SKILL.md`, so
the session knows to write it.

**PR desk sidebar**: `renderDesk()`, `renderDeskDrawer()` and the `desk*` functions in
`index.html`; the `desk` object in the state; `pr-desk/SKILL.md` for board mode.

## Trying a change

The page re-reads `index.html` on every load, so a UI change needs only a browser refresh.
A `server.py` change needs a restart; the URL stays the same.

To try it without a live run:

```bash
mkdir -p /tmp/board-try && cp board/example-state.json /tmp/board-try/board-state.json
python3 board/server.py --dir /tmp/board-try   # prints BOARD_URL; open it
```

Clicks land in `/tmp/board-try/decisions.jsonl`. To see how a card reacts, edit
`board-state.json` by hand, as the session would.

To restart a live run's server:

```bash
pkill -f "board/server.py --dir $HOME/.claude/orchestrate-my-tickets/runs/<run>/board"
nohup python3 board/server.py --dir ~/.claude/orchestrate-my-tickets/runs/<run>/board \
  > ~/.claude/orchestrate-my-tickets/runs/<run>/server.log 2>&1 &
```
