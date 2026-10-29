---
name: pr-desk
description: Use when asked to start the PR desk, run /pr-desk, or run a long-lived session that handles PR reviews, fixes and merge conflicts on my own PRs, and approvals of PRs I reviewed. Work that needs no input (merge conflicts, approvals, migration reorders) runs and pushes in background sub-agents on its own. Anything that needs the user lands in a numbered inbox list that is reprinted as it grows; the user types a number, then decides that item's choices in AskUserQuestion pop-ups.
user_invocable: true
---

# PR Desk

The main session is a switchboard: it starts background agents, keeps the **inbox**, and relays. It never reads diffs, code or full thread bodies itself.

The inbox and outcome lines are plain text. `AskUserQuestion` is used only **after the user picks an inbox item**, to take that item's decisions. It never interrupts on its own.

## Board mode

When `/orchestrate-my-tickets` has its board up, the desk runs inside that session and the
board's **PR desk sidebar** replaces the terminal inbox. Everything below still holds, with
these swaps:
- **Inbox:** write it to `desk.inbox` in the board state instead of printing it. Running and
  queued agents go to `desk.running` / `desk.queued`, and outcome lines go to `desk.outcomes`
  (`{text, ok}`), plus a toast.
- **Decisions:** never call `AskUserQuestion`. Each sub-item carries its options with the
  recommendation as `recommended`:
  - **fix:** one single-choice sub-item per thread, with options Fix / Skip / Defer
    (recommended first) and the gist and approach as `text`. The user's note is the approach
    or reply text.
  - **review and follow-up:** one checkbox sub-item per finding or thread, with
    `recommended: true` on the ones to act on.
  - **review concerns:** a single-choice sub-item with Continue to code review / Stop here.
- `desk_decide` with `all_rec` is the board's `N all rec`.
- `desk_drop` abandons item `desk`: post nothing, tell its agent to stop and remove its worktree, drop the item, and add an outcome line.
- A pasted URL arrives as `desk_review`, and start / stop as `desk_start` / `desk_stop`.
- **Watcher:** skip the `Monitor` in Start step 2, because it expires every 30 minutes and leaves
  gaps. Instead, run `nohup bash watch-prs.sh >> <run>/desk-events.log &` (the board's run home, so a resumed run keeps its desk) and wait on
  that log with the same "wait for the file to grow" background command the board uses for
  decisions. Start the waiter again after each event. Kill the watcher on `desk_stop`.

## Start

1. `rm -f ~/.claude/skills/pr-desk/state/*.json` so that pending work from before this session is reported again.
2. Arm the watcher with `Monitor`: command `bash ~/.claude/skills/pr-desk/watch-prs.sh`, description `pr-desk watcher`, `timeout_ms: 1800000`. When it expires, re-arm it silently.
3. Print: `PR desk on. Paste PR URLs to review; type a number to work an inbox item.`

## Two lanes

**Autopilot: no input, the agent pushes.** The user only ever sees the outcome line.
- `conflict: <url>` → **conflict** agent.
- `approve: <url>` → **approve** agent.

**Inbox: needs the user.** An agent first does its read-only part in the background. Its decision list then becomes an inbox item.
- `fix: <url>` → **fix** agent, phase 1.
- A PR URL pasted by the user → **review** agent, phase 1.
- An approve agent that finds the PR partly addressed → follow-up-comment item.
- Any agent that hits something it must not guess → its own item.

Keep at most 4 agents running at once. Queue the rest in order and start them as slots free up. Never run two agents on one PR: queue the second event and start it when the first finishes, since the watcher won't re-send it.

## The inbox

A numbered list kept in working memory. One line per item:

```
INBOX
1. core#6181  fix       12 comments (8 rec fix, 4 rec skip)
2. core#6200  review    3 findings, 1 concern
3. snowflake#850  follow-up  2 threads unaddressed
```

- Reprint the whole inbox whenever an item is added or removed. Also reprint it after an outcome line, and when the user types `inbox`.
- Numbers stay stable while the session runs. Done items are dropped, and a new item takes the next number.
- Before you show or act on an item, re-check it with `gh pr view <url> --json state,mergeable` and the threads' `isResolved`. If the PR is merged or closed, or the item is no longer pending, drop it quietly and tell the agent to clean up.

### Working an item

User types `N`, then take the decisions with `AskUserQuestion` (4 questions per call; repeat until every sub-item is covered). Prefix each question with `repo#N`.
- **fix:** one single-select question per thread. The question text is the reviewer, the gist and the proposed approach or skip reason. The header is `path:line`-ish, at most 12 chars. Options: the recommendation first, marked `(Recommended)`, then the other two of Fix / Skip / Defer. A free-text answer via Other is the user's note: pass it through verbatim as the approach or the reply text.
- **review:** `multiSelect`, 4 findings per question. Label `path:line`, description = title + why. Product/architecture concerns go first. When there are concerns, add a single-select **Continue to code review / Stop here**.
- **follow-up:** `multiSelect` over the unaddressed threads. Selecting none means no comment is posted.

Then resume the agent with `SendMessage`, passing the decisions in compact form. Drop the item and reprint the inbox. When the agent finishes, print its outcome line.

`N all rec` skips the pop-ups and accepts every recommendation.

## Agent prompts

All agents are `subagent_type: general-purpose` and run in the background. Every prompt ends with the **Return rules**.

**Worktree setup** (fix, conflict): run `gh pr view <url> --json headRefName,baseRefName`. Then `git -C ~/Desktop/work/<repo> fetch origin <headRef> <baseRef>`, then `git -C ~/Desktop/work/<repo> worktree add ~/Desktop/work/.worktrees/<repo>-<N> origin/<headRef>`, then `git switch -C <headRef> --track origin/<headRef>` inside it. If the branch is checked out elsewhere, stay on a detached HEAD and push with `git push --no-verify origin HEAD:<headRef>`. Clone into `.worktrees` if the repo isn't on disk. Never touch the main checkout. Copy `.npmtoken` from `~` when needed. Stage only the files you changed. Always push with `--no-verify`. Remove the worktree at the end.

### conflict (autopilot)
> My PR `<URL>` conflicts with its base. Fix it with the `fix-pr-conflicts` skill, with no questions: never call AskUserQuestion. <Worktree setup>
> - Resolve every hunk, choosing by the intent of both sides. When each side adds independent lines, keep both.
> - If the PR adds a Prisma migration whose timestamp isn't after the newest one on the base for that service, rename it to the current UTC timestamp.
> - If the PR is in a stack and the conflict comes from a base further down, merge each PR's base into it, from the lowest affected PR upward. Use the `gh stack` CLI where it applies.
> - Run the scoped typecheck, lint and tests for the touched projects. A failure that's clearly unrelated (known flaky spec, pre-existing) counts as passing; say so.
> - Then push, re-request dismissed reviewers and send the Slack pings, per the skill.
> - Only if the checks fail because of your resolution: don't push, and return `decision-needed` with the failing check and the hunk.

### approve (autopilot)
> Run the `approve-addressed-prs` skill scoped to `<URL>` only (skip step 1's search; skip the PR if I already approved). Do steps 2–5 as written. Step 6: never call AskUserQuestion. If the PR is partly addressed, return the unaddressed threads as the decision list and wait. When resumed with selected threads, post the follow-up comment per step 6.3.

### fix (inbox)
> Handle unresolved review threads on my PR `<URL>` using the `fix-pr-comments` skill. <Worktree setup>
> - Phase 1 (now): do steps 1–5c only, and read the code for each thread. Never call AskUserQuestion. Make no edits and post nothing. Return the decision list. Leave the worktree in place.
> - Phase 2 (when resumed with decisions): apply them per step 5d with no further questions. Use the user's note as the approach where there is one, otherwise your proposed approach. Run the scoped checks. Then do steps 6–7 as written: commit, push, replies, resolve, re-request, Slack, auto-merge. Leave auto-merge off if the PR is a draft or its body says to wait. If a fix turns out bigger than proposed, stop and return a new one-item decision list.

Decision list item: `thread id | path:line | reviewer | gist ≤2 lines | Fix/Skip/Defer | approach or reason ≤2 lines`.

### review (inbox)
> Review `<URL>` by running the `review-pr` skill. Never call AskUserQuestion. At step 3's gate and at step 6, don't ask: return the decision list (concerns, then blocking findings) and wait. Post nothing until resumed. When resumed with selections, post exactly those per steps 7–9. If nothing was selected, approve per step 8 when the skill allows it. Then return the step 9 line.

Decision list item: `id | path:line or concern | title ≤8 words | why ≤1 line`.

## Return rules (append to every agent prompt)

> Check `gh pr view <url> --json state` before any work, and again right before returning a decision list. If the state isn't OPEN, clean up and return `STATUS: done`, "PR is <state>".
> Your final message is read by a coordinator with limited context. Keep it under 15 lines, and give no diffs, code or full comment bodies. Start with `STATUS: decision-needed | done | failed`, then the PR URL, then either the decision list (one item per line, fields separated by ` | `) or a single outcome line (with the commit hash or review URL where one exists). Never ask the user anything yourself.

## Reporting

- Autopilot outcomes: one line each, for example `✓ core#6135 conflict fixed — 786c088cf6`, `✓ snowflake#846 approved`, `✗ core#6153 conflict — tests fail after merge (inbox 4)`.
- Watcher `watcher error: ...`: one line. Say nothing more unless it repeats.
- `status`: agents running and queued, plus the inbox.

## Stop

`stop desk` → `TaskStop` the watcher. List the agents still running and the inbox. Start nothing new.
