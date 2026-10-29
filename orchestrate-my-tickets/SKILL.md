---
name: orchestrate-my-tickets
description: Works a batch of tickets — a sprint, an epic, a status column, or a pasted key list — in parallel at every stage, by running `orchestrate-ticket` in one worktree-isolated sub-agent per ticket and keeping every gate in the main session. One state and readiness sweep across the whole set, a confirmation gate before anything is dispatched, then rounds - agents work until their first gate and report back, the main session dispatches the independent verifiers, puts every pending write and question on a localhost kanban board where the user approves on the card, makes each approved write, and resumes that agent - until every ticket waits on someone outside the run. Covers holding a dependent or file-overlapping ticket until the ticket it depends on has its PR open, running one promote for the whole batch, and collecting the final table from the board rather than from the agents. Use for "work all my sprint tickets", "run orchestrate-ticket on each of my tickets in sub-agents", or any batch of tickets at mixed stages that should move on together. To only turn ready tickets into PRs, with agents that open them themselves, use dispatch-ready-tickets. Skip for a single ticket — that is `orchestrate-ticket` inline.
---

# Orchestrate My Tickets

Read [runtime bindings](/Users/omercohen/Desktop/work/orchid-plugins/plugins/orchid/RUNTIME.md) before resolving bundled paths, connected tools, or delegated roles.

A batch of tickets in. A table of where each one landed out, with the user asked only once
per round. The sub-agents do the work. The main session holds the gates: every Jira and
GitHub write, every push, the independent verifier, and the promote. A sub-agent cannot ask
the user a question, cannot start an agent of its own, and must not write outside its
worktree. So it stops at its first gate and reports. The main session collects the reports
from every ticket, asks the user once, and sends the agents back to work.

## When to use

- "Work all my tickets in the sprint" / "run `orchestrate-ticket` on each of my tickets in a
  sub-agent".
- To only turn ready tickets into PRs, use `dispatch-ready-tickets`. Its agents open PRs
  and post comments themselves. This skill keeps every write in the main session.
- Skip for a single ticket — run [`orchestrate-ticket`](/Users/omercohen/.claude/skills/orchestrate-ticket/SKILL.md)
  inline; a fan-out of one costs an agent boot for nothing.
- Skip a ticket whose change spans repos: worktree isolation is per repo, so that one is
  worked inline, outside the batch.

## Prerequisites

Read before executing the workflow:
- [`_shared/jira-access.md`](/Users/omercohen/Desktop/work/orchid-plugins/plugins/orchid/skills/_shared/jira-access.md) — JQL mechanics, the `hasNextPage` trap, batch confirmation, and why a sprint's membership is history rather than state.
- [`_shared/pr-push-authorization.md`](/Users/omercohen/Desktop/work/orchid-plugins/plugins/orchid/skills/_shared/pr-push-authorization.md) — every push is shown and approved; the batch table must name each PR, branch and commit.
- [`_shared/jira-comment-template.md`](/Users/omercohen/Desktop/work/orchid-plugins/plugins/orchid/skills/_shared/jira-comment-template.md) — the shape of every comment the main session posts.
- [`_shared/definition-of-done.md`](/Users/omercohen/Desktop/work/orchid-plugins/plugins/orchid/skills/_shared/definition-of-done.md) — an open PR is not a closed ticket; the final table reports what each ticket still owes.

Skills in this plugin:
- `/orchestrate-ticket` — what every dispatched agent runs, in its **delegated mode**. Read
  that section: it fixes what an agent may do and the report it returns.
- `/review-ticket-readiness` — phase 1's sweep for tickets not yet started.
- `/implement-ticket` — steps 5 and 6 (strip comments, push, open the PR) run in the main
  session for every implement-stage ticket.
- `/verify-ticket-in-dynamic-env` — the pre-merge check, dispatched to a fresh agent.
- `/query-jira-api` — the bulk ticket read; the Atlassian MCP truncates a sprint sweep.
- `promote-tickets` from the `core` plugin — run once per round for every ticket in a
  `Ready For …` column. If it is not installed, report those tickets as waiting.

Agents in this plugin:
- `ticket-verifier` — grades each implement-stage diff. Always dispatched by the main
  session, never by the ticket's agent, and never the agent that wrote the code.

Inputs, all optional, in plain words after the command:
- The ticket source — a sprint number, an epic key, a status column, or an explicit key list.
  **None given:** resume the most recently changed run home (`ls -t ~/.claude/orchestrate-my-tickets/runs | head -1`);
  if there is none, use "my current sprint". Do not ask.
- The repo, if it is not `core`.
- Any steering, e.g. "keep CORE-1234 inline", "plan only, don't dispatch".

## The run home, and resuming

A run outlives its session. Everything the board shows lives in a **run home**,
`~/.claude/orchestrate-my-tickets/runs/<run>/` (`<run>` names the source, e.g. `sprint-76`),
never in the session scratchpad, which a reboot wipes:

- `run.json` (the per-ticket layer), `sprint.json`, `jira/` dumps, `build_state.py`, `sync.sh`
- `board/`: `board-state.json`, `decisions.jsonl`, `cursor`, `server.json` (port and token)
- `desk-events.log`, `desk-cursor`, and every draft (`<KEY>-comment.md`, `<KEY>-pr.md`, …)

Bulky evidence (logs, data dumps, customer data) stays in the scratchpad; a card that needs
it names the file, and a resumed run treats a missing one as gone.

When you dispatch an agent, record its `agentId` and transcript path
(`~/.claude/projects/<project>/<session>/subagents/agent-<id>.jsonl`) on its ticket in
`run.json`, appending to `agents[]` so earlier ones stay listed.

**On start, look for a run home for the same source first.** If one exists, resume instead
of phase 1 and 2:

1. Start the server on it (below). `server.json` gives the same URL, so open tabs and
   bookmarks keep working.
2. Restart `sync.sh` and rebuild the state, so Jira changes made while the run was down land
   as toasts.
3. Sub-agents die with their session. Every ticket whose `agent` is `queued`, `working` or
   `at_gate` becomes `stopped`, with an activity line "session ended". Its pending writes and
   questions stay on the card: they carry their exact payload, so an approval is still
   valid, and you act on it as usual. The step 10 re-read before every write covers what
   changed in between.
   The PR desk's agents die too: move each `desk.running` entry back to `desk.queued` so it
   starts again. Its inbox items stay, with their `agentId` for the new agent to read.
4. Handle every decision past `cursor`, then re-arm the waiters.
5. **Dispatch agent** on a stopped card briefs the new agent with the card's activity,
   replies and answered questions, and the transcript paths in `agents[]`: "read the prior
   agent's transcript before redoing anything it did". Its `closed` facts are re-checked
   against Jira and GitHub, as for any dispatch.

## The board

The run's only approval surface: a kanban of the batch in Jira-status columns, served from
localhost. The session writes what you see; you approve on
the cards; the session acts. The terminal only logs what happened.

- **Start it** after step 1, in the background:
  `python3 <this skill>/board/server.py --dir <run>/board`. It prints
  `BOARD_URL=http://127.0.0.1:<port>/?t=<token>`. Open that URL (`open "$URL"`) and print it.
  It binds `127.0.0.1` only and rejects any request without the per-run token. It keeps the
  port and token in `board/server.json` (mode 600), so a restart serves the same URL; if that
  port is taken it keeps the token and takes a new port.
- **Keep it live from Jira.** Start a background loop that re-runs the phase-1 JQL every 2
  minutes and rebuilds the state. Jira owns `status` and sprint membership: never pin a status
  in your per-ticket layer, or the card stops following Jira. A ticket that appears in the
  sprint after the sweep gets a "new" card (`group`/`agent` waiting, with **Dispatch agent**).
  A status that changed since the last build gets a toast.
- **Write state** to `<run>/board/board-state.json` whenever anything changes: write a
  `.tmp` and `mv` it over, never write in place. Shape: [`board/example-state.json`](board/example-state.json).
  `columns` are the board's Jira statuses in order. Each ticket carries its Jira fields plus
  `stage`, `group`, `deps`, `readiness`, `agent` (`queued` / `working` / `at_gate` /
  `waiting` / `stopped` / `done`), `waitingOn`, `pr`, `verifier`, `activity`, `replies` (`[{id, text, ts}]`: agent answers that ask nothing of the user; anything that asks goes in `questions` with options, never in a reply), and every
  pending write and question with a stable `id`. A pending write names its exact target and
  full payload, the same as the table this skill used to print. `kind: "push"` and
  `kind: "run"` are never editable. A `run` item is one exact command against a shared
  environment (target names the environment and region); its `approve` runs exactly that
  command in the main session and sends the output back to the ticket's agent. Bodies and question text are Markdown; the board renders them (sanitized). Every
  question carries a `recommended` answer. A question with a fixed set of choices also
  carries `options` (strings, the recommended one among them), and the board shows one
  button per option. Push a `toasts` entry for each transition you make.
- **Read decisions** with a background shell command that waits for the file to grow past a
  **cursor** (`<run>/board/cursor`, the number of lines already handled), prints every
  new line, and exits. Handle **all** printed lines, then write the new line count to the
  cursor and start the waiter again. Never take the baseline from `wc -l` at restart: clicks
  that land while you are handling the last batch are then skipped and stay "pending" on the
  board for ever. A `Monitor` on `tail -F` expires every 30 minutes and leaves gaps.

  ```bash
  n=$(cat "$D/cursor"); until [ "$(wc -l < "$D/decisions.jsonl")" -gt "$n" ]; do perl -e 'select(undef,undef,undef,1)'; done; tail -n +"$((n+1))" "$D/decisions.jsonl"
  ```

  The page also calls `GET /decided` on load, so a refresh keeps showing what was sent.

  Each line is one decision: `{id, ts, action, ticket, item, body?, note?, plan?, tickets?}`.

  | action | do |
  |---|---|
  | `dispatch` | phase 2's confirmation: apply `plan` (per key `group`, `excluded`), then step 7. A per-key `prompt` (from the drawer's prompt box) becomes the brief's instruction in place of `open`. Mid-run, the **Dispatch agent** button (on every card with no agent queued, working or at a gate, including `done`) sends a one-key `plan`: re-read that ticket (step 2's state for it, and step 3 if it is not started), then step 7 for it alone. With `fresh: true` (**Re-dispatch fresh**): stop the ticket's agent if one is running, drop every pending write and question on its card without posting, clear its activity, re-read the ticket from Jira and GitHub from scratch, and brief the new agent only from that read. Prior board notes are not `closed` facts. If the ticket has a worktree with uncommitted changes, set them aside first (`git -C <worktree> stash push -u -m "fresh-redispatch <KEY> <UTC time>"`) so the new agent starts from the branch's committed state. Record the stash ref in the card's new activity, and name any unpushed local commits in the brief. Never drop a stash and never reset commits. Never undo anything already written |
  | `approve` / `edit_approve` | re-read the ticket, make the write (with `body` verbatim for `edit_approve`), read it back |
  | `send_back` | message the ticket's agent with `note`; it redrafts and the item comes back |
  | `drop` | remove the item; tell the agent it was dropped. On a reply item (`note: "resolved"`) just remove it |
  | `answer` | message the ticket's agent with `body`. On a reply item it is a follow-up: same agent, same context |
  | `stop_agent` | stop the sub-agent, keep its worktree; set `agent: "stopped"` |
  | `move_to_waiting` | **Park**: stop if running, set `group`/`agent` to `waiting`, `waitingOn: note`. With `clear: true` (its "also drop drafts and questions" box): also drop every pending write and question on the card without posting, so the ticket parks clean. Write nothing |
  | `promote` | run `promote-tickets` once for `tickets`, up to its confirmation. Put that confirmation on the promoted tickets' cards as a `kind: "promote"` pending write: template ref, exact `values`, source → target versions, prerequisites checked. Its `approve` triggers it. |

  After acting, take the item off the card and add an `activity` line. Never act on a
  decision whose `item` is no longer on the card. That is a stale click.
- **The PR desk sidebar.** The board also hosts `/pr-desk` in **board mode** (see that
  skill). State lives under `desk` in the same file: `{on, running[], queued[], inbox[],
  outcomes[]}`. An inbox item is `{n, pr, url, kind, summary, text?, items[]}`. A sub-item
  with `options` (plus `recommended`) is a single choice, such as Fix / Skip / Defer per
  thread. A sub-item without `options` is a checkbox, preselected when `recommended: true`,
  such as review findings or follow-up threads. Decisions arrive on the same channel:

  | action | do |
  |---|---|
  | `desk_start` / `desk_stop` | start or stop `/pr-desk` in board mode |
  | `desk_review` | queue a review agent for `url` |
  | `desk_drop` | abandon inbox item `desk`: post nothing, tell its agent to stop and clean up, drop the item, add an outcome line |
  | `desk_decide` | resume inbox item `desk` with `answers` (`{itemId: {choice, note?}}`) and/or `selected` (ids), or `all_rec: true` |

  Re-check the PR before acting, as `/pr-desk` says. The desk's agents count toward their own
  limit of 4, separate from the ticket agents.
- **If the server dies**, say so and restart it on the same run home: the URL is unchanged.
  If it will not start, fall back to asking in the terminal with one table, as step 9 describes.

## Phase 1 — sweep the whole set once, in the main thread

1. **Resolve the set, then show it before anything else.** For "my sprint tickets":

   ```bash
   JIRA=(python3 "$ORCHID_PLUGIN_ROOT/tools/jira.py")
   "${JIRA[@]}" search 'project IN (CORE, CON) AND sprint = "Core & Applications Sprint <n>" \
      AND statusCategory != Done AND assignee = currentUser()'
   ```

   Print key, summary, type, status. A wrong JQL otherwise burns the whole fan-out.

2. **Read the state of every ticket in one pass.** Status and links from the search; PRs
   by key (`gh search prs <KEY> --owner Orchid-Security`), with state, CI and the head
   branch. Also check each ticket-named worktree for a live lock, as in `orchestrate-ticket`
   step 2. A ticket another session holds right now goes in the waiting group, named with
   the worktree and pid that hold it. This is cheap, and it settles which tickets need an
   agent at all.

3. **Grade readiness for the tickets not yet started** (`Opened` / `Ready For
   Development` with no PR), with `review-ticket-readiness`, audience **dispatched
   agent**. Capture each Done-when verbatim, the resolved identifiers and the file
   references. They become the agent's `closed` facts, so `implement-ticket` step 2 is
   not re-run per agent.

4. **Sort every ticket into one of four groups:**

   | Group | Means | Gets an agent? |
   |---|---|---|
   | dispatch | it has work an agent can do now | yes |
   | promote | in `Ready For Staging` / `Ready For Production` | no — phase 3 runs one promote for all of them |
   | waiting | only someone outside can move it: a reviewer, a deploy, a product owner | no — reported with who it waits on |
   | inline | spans repos, or the user asks to keep it in the main session | no — worked after the batch |

5. **Name the dependency edges.** A ticket gets `deps: [<KEY>]` when its branch would
   base on that ticket's, or when both touch the same files. Verify-stage and read-only
   tickets touch no files and have no deps. The edges are what the gate decides.

## Phase 2 — the confirmation gate

6. **Put the plan on the board and stop.** Write the state with `run.phase: "planning"`.
   Per ticket: the status, the stage, the group, `deps`, and for a not-ready
   ticket its failing readiness clause. **Nothing has been written and nothing
   dispatched.** The user prunes and re-groups on the cards, then presses
   Dispatch. Never dispatch without a `dispatch` decision. Then set `run.phase: "running"`.

## Phase 3 — rounds until everything waits on someone outside

7. **Dispatch: one agent per ticket whose `deps` all have a PR open.** The rest show `queued` and start as their deps' PRs open. An agent that writes code (implement or
   review stage) gets its own worktree of the ticket's repo. The host's
   `isolation: "worktree"` checks out the session's own repo, so it fits only when the
   session runs in the ticket's repo. Otherwise, create the worktree in the main session
   (`git -C <repo> worktree add <path> -b <branch> origin/main`), and name its path in the
   brief. Reuse an abandoned worktree from step 2 instead of adding one. A read-only agent
   (verify, readiness, refine, triage, unblock) gets no worktree: a checkout of this repo
   would cost a boot and serve nothing. Each brief says to run `orchestrate-ticket` in
   **delegated mode** for its single ticket, and carries:
   - `closed` — the phase-1 facts, stated as fact: the stage, the Done-when verbatim, the
     identifiers, the PR and branch. Say plainly that they are not to be re-derived.
   - `open` — only what genuinely needs work. **If it is empty, do not dispatch.**
   - its per-ticket draft file names in the run home (`<KEY>-comment.md`, `<KEY>-pr.md`), and that
     every comment dump goes to the scratchpad (`jira.py comments --out <scratchpad>`), never into
     a repo checkout.
   - that a closed fact it finds wrong is the report, not something to work around.

8. **Collect the reports, then handle what needs an agent.** For every `needs_agent:
   ticket-verifier`, dispatch a fresh `ticket-verifier` on that branch and sha. On
   **FAIL**, send the verifier's report back to the ticket's own agent (the host's agent
   messaging facility, so it keeps its context), and verify its new head with another
   fresh verifier. Two rounds at most, then report both verdicts and stop that ticket.
   For a PASS, do `implement-ticket` step 5 (strip comments) in the main session, and
   prepare step 6's push and PR as pending writes. The agent drafted the PR body before
   the verifier ran, so add the verifier's verdict to the body yourself. A `needs_agent` dynamic-env check
   goes to a fresh agent running `verify-ticket-in-dynamic-env`, never the author.

9. **Re-read the ticket, make its transitions, then put its card in front of the user.**
   This is per ticket, as each report arrives, not per round. First re-read the reporting
   ticket's status, comments and changelog. Anything that changed since the sweep was not
   seen by its agent. Drop every pending write the board already shows done.
   A change from the user's own account means another session is working the ticket, even
   with no worktree lock to show it. Move that ticket to waiting, and write nothing on it.
   Transitions need no confirmation: make
   each one an agent recommended, announce it as a toast, and read it back. Put everything
   else on the ticket's card: each pending write with its exact target and payload
   (comment body, commits and branch to push, PR title and body, sub-task fields), and
   each question with who can answer it. An approval is valid only because the card showed
   the exact target and payload. Set `agent: "at_gate"`.

10. **Act on each decision as it lands, then resume that ticket.** Re-read the ticket just
    before its write: the user may have approved minutes after the card went up. Post the
    write, read it back, then message that ticket's agent with the result and the user's
    answers, and it carries on to its next gate. Other tickets do not wait for it. Keep
    `promote.tickets` in the state current. When the user presses Promote, run
    `promote-tickets` once in the main session for all of them. Every confirmation or
    choice that skill asks for goes on the board as a pending write or question, never into
    the terminal.

11. **Repeat from step 8** until no agent has work left. A ticket leaves the loop when its
    report says it waits on someone outside the run, or when it is done. Dispatch a queued
    ticket as soon as every ticket in its `deps` has its PR open.

## Phase 4 — collect

12. **Read the board, not the agents.** Per ticket: the status, the PR, the
    `ticket-verifier` verdict, any environment verdict, and what it still owes against
    the definition of done. An agent's verdict is a claim; the comment and the PR are what
    the team reads.

13. **Report one table**: ticket, where it landed, and who or what it waits on. That
    table is the artefact of the run; the per-agent reports are not.

## Critical gotchas

- **The board is the only approval channel while it is up.** Do not also take approvals in
  the terminal: a write approved in one place and still pending in the other is how a
  comment gets posted twice. The terminal table is only the fallback when the server is down.
  This covers the skills the run calls, too: a choice or confirmation that `promote-tickets`,
  `review-ticket-readiness` or any other skill would ask in the terminal goes on the card.
- **The token is the board's whole security.** Any website open in the user's browser can
  POST to localhost. Never print the URL anywhere but this session, never serve without the
  token, and never bind to anything but `127.0.0.1`.

- **The main session is the only one that talks to the user and writes.** A sub-agent that
  posts a comment, pushes or transitions has stepped outside delegated mode. Its result
  still needs the main session's read-back, and the run should say what it did.
- **Hoist the readiness grade, or pay for it N times.** `implement-ticket` runs
  `review-ticket-readiness` as its own step 2. Leaving it there costs a re-grade per
  ticket and can return a *second, different* verdict on one already graded. Measured
  shape: on the CORE-4576 run four dispatched agents burned ~345k tokens and ~200 tool
  calls re-reading one ticket 4x, `AGENTS.md` 4x, and re-running the same green suites.
  The briefs caused it, not the agents.
- **One promote for the batch, never one per ticket.** A promote moves services, and every
  ticket merged into a service between the two versions ships. Two promotes in flight for
  overlapping services race each other.
- **A dependent ticket cannot be graded while its base is unmerged.** A PR based on
  anything other than `main` gets **zero** dynamic-env runs — `core`'s `pr.yaml` filters
  `branches: [main]`. `deps` exist for this reason: dispatching a chain at once silently
  drops the gate on every link but the first.
- **Worktree isolation is not environment isolation.** Each agent gets its own checkout
  and its own dynamic namespace, but the dev Snowflake is *shared*, and rows a probe
  writes there outlive the namespace. Delegated agents are read-only on environments, so
  any seeding is a main-session write the user approves, with its own fixture space and
  never on the e2e organisation.

Further traps in [`dispatch-ready-tickets/references/extended-gotchas.md`](/Users/omercohen/Desktop/work/orchid-plugins/plugins/orchid/skills/dispatch-ready-tickets/references/extended-gotchas.md). They apply here too.

## References

- `../dispatch-ready-tickets/references/extended-gotchas.md` — the further traps: brief anti-patterns, stale closed facts, sprint membership as history, choosing the readiness audience, and the shared scratchpad.
