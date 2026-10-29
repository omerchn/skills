---
name: orchestrate-ticket
description: The single entry point for working one Jira ticket across sessions — works out which stage the ticket is in (triage, refine, implement, review, verify, promote, unblock) from its status, comments, links, changelog and the live branch / PR / deploy state, then runs the skill that owns that stage from where the last session stopped. Writes nothing to Jira of its own. Has a delegated mode for running one ticket in a sub-agent that returns at its first gate. Use when asked to work on, continue, resume, pick up or "keep going on" a ticket by key, or to say where a ticket stands and what comes next. For a batch of tickets, such as all of a sprint's, use `orchestrate-my-tickets`, which runs this skill per ticket.
---

# Orchestrate Ticket

Read [runtime bindings](/Users/omercohen/Desktop/work/orchid-plugins/plugins/orchid/RUNTIME.md) before resolving bundled paths, connected tools, or delegated roles.

This skill is a router: it does no stage work itself. It reads where the ticket is, then
hands it to the skill that owns that stage. It keeps no state of its own. The ticket and
the code already hold it: the status, the comments the stage skills post, the branch and
the PR. It keeps every gate of the skill it hands off to: confirmations, the
implementer/verifier split, push authorisation.

## Prerequisites

Read before executing the workflow:
- [`_shared/jira-access.md`](/Users/omercohen/Desktop/work/orchid-plugins/plugins/orchid/skills/_shared/jira-access.md) — status ladder, transition ids, and write rules.

Inputs to gather from the user: the ticket key. Nothing else up front.

## Workflow

1. **Read the ticket.** With `/query-jira-api`, read the issue (type, status, resolution,
   parent, sub-tasks, links), every comment, and the changelog. Write comment dumps to a
   scratch directory, never into a repo checkout.

2. **Find the work.** Search PRs by key across the org (`gh search prs <KEY> --owner
   Orchid-Security`). Then look for branches with the key in their name, on the remote and
   in local worktrees (`git worktree list`). A local branch or worktree with commits that
   aren't pushed holds work that exists only on this machine. Say so. A worktree that
   `git worktree list` shows as `locked` belongs to an agent. Its lock file
   (`.git/worktrees/<name>/locked`) names the agent's pid, so check that pid with `kill -0`:

   | Lock | Means | Do |
   |---|---|---|
   | locked, pid alive | another session is working the ticket now | Stop. Report which worktree and pid hold it. Never start a second run on the same ticket. |
   | locked, pid dead | that session ended, maybe mid-work | Resume from its commits that aren't pushed yet. Don't start over. |
   | not locked | a plain worktree | Use it as found. |

   For each PR, check
   its state, CI (`gh pr view --json state,mergedAt,statusCheckRollup`) and unresolved
   threads. Threads come from the GraphQL `reviewThreads { isResolved isOutdated }` query
   that `fix-pr-comments` uses; `gh pr view` cannot answer it. If the PR has merged, check
   which environment runs it.

3. **Rebuild the state from the evidence.** Put down what each piece of evidence settles:

   | Evidence | Settles |
   |---|---|
   | A readiness review or Done-when comment, with no description edit after it in the changelog | the readiness grade and the Done-when |
   | A triage comment and sub-tasks | root cause known; the work moves to the sub-tasks |
   | An implementer or verifier result in a comment or the PR body, at a sha | that verdict, for that sha only |
   | A dynamic env or environment verdict comment | that verdict, for that environment |
   | A comment that asks a question nobody has answered | an open question; name who it waits on |
   | An open "is blocked by" link | a blocker; it matters only if it stops the next step |

   Newer evidence beats older. A verdict at an older sha says nothing about a newer head.
   A description or Done-when edit after a grade means grading again.

4. **Pick the stage.** First bring the status up to the live state. A ticket still in
   `Opened` or `In Progress` with a merged PR missed its moves, so walk the ladder in
   `jira-access.md` up to `In Review`. The merged-PR row below takes it from there. Then
   take the first row that matches:

   | Ticket is | Stage | Hand to |
   |---|---|---|
   | `Closed` | done | Report the resolution and stop. Reopening is the user's call — see `jira-access.md` on `resolution`. |
   | `Blocked`, `Need more data`, `Pending Support`, or an open blocker stops the next step | unblock | `resolve-ticket-blockers` |
   | A `Production Bug`, any other status | triage | `triage-and-fix-prod-bug`. It resumes from status. Each sub-task it creates runs through this skill on its own key. |
   | `Opened` / `Ready For Development` with no readiness grade | readiness | `review-ticket-readiness` |
   | the same, graded *needs a Done-when* | refine | `author-ticket-done-when`, then grade again |
   | the same, graded *needs product input* or a bad shape | refine | `refine-jira-ticket`. Stop once the question is put to its owner. |
   | the same, graded *ready to dispatch* | implement | `implement-ticket` step 1, then step 3, with the grade as a fact |
   | `In Progress`, no branch or PR | implement | `implement-ticket` step 1, then step 3 |
   | `In Progress`, a branch but no PR | implement | `implement-ticket` at step 4 if no verdict exists for the branch head, else step 5 |
   | `In Review`, PR open, CI red | implement | `implement-ticket` to fix the failing check, then back to step 4 |
   | `In Review`, PR open with unresolved threads | review | `fix-pr-comments`, then `implement-ticket` step 4 if behaviour changed |
   | `In Review`, PR open, no threads | review | `implement-ticket` steps 7–9 if there is no dynamic env verdict yet; otherwise report that it is waiting on review and stop |
   | `In Review`, PR closed unmerged | implement | Follow a replacement PR if the PR or ticket names one; otherwise `implement-ticket` from the last pushed head |
   | `In Review`, every PR merged, in a repo with no environments (plugins, tooling) | verify | The first release tag that contains the merge is the deploy. Run the Done-when against that tagged code, then close per `definition-of-done.md`: a verdict comment, `Closed`, and resolution `Done` written separately. These tickets skip the testing columns; CORE-5143 and CORE-5245 went straight to `Closed`. |
   | `In Review`, every PR merged | verify | `verify-ticket-deployed` for dev. Deployed: move to `Testing In Dev` (`131` on CORE, resolved live), then the next row. Not yet: report that it is waiting on the dev deploy and stop. |
   | `Testing In Dev` / `Testing in Staging` / `Testing In Production` | verify | `verify-ticket-deployed`, then `verify-ticket-behaviour` for that environment |
   | `Ready For Staging` / `Ready For Production` | promote | `promote-tickets` from the `core` plugin. If it is not installed, say so and stop. |

   Say which row matched and why, in one line, before handing off.

5. **Resume, don't restart.** Give the stage skill what step 3 settled, as facts, each with
   the comment or command it came from, and the step to start at. It must not re-run a
   gate whose result is already on record for the current head.

6. **Keep going until someone else has to act.** When a stage finishes and the next one can
   start now, go back to step 4. Stop when the next step waits on someone else: a
   reviewer, a promote held for untested ride-along tickets, a producer run, a product
   decision. Before stopping, tell
   the user in chat where the ticket stands, what comes next, and who or what it waits on.
   Write nothing to Jira for this. The comments and transitions the stage skills make are
   the record the next session reads.

## Delegated mode

Use this mode when a batch run (`orchestrate-my-tickets`) runs this skill in a
sub-agent. The agent works without the user. It goes as far as it can, and it returns to
the main session at the first step that needs the user, a write, or another agent. Steps 1
to 5 run unchanged. Step 6 changes: the agent stops at the first gate, not only when
someone else has to act.

The agent may read anything; write code, run targeted local tests and create a local branch
in its own worktree; and run read-only checks against dev, staging or production. It must
not:
- ask the user anything. Put the question in the report.
- write to Jira at all, transitions included. A delegated agent recommends a transition and
  never makes it.
- commit, push, open or edit a PR, or post on GitHub.
- promote, trigger, seed or otherwise write to any environment.
- dispatch another agent. A sub-agent cannot nest one.

What each stage does here:

| Stage | Delegated agent |
|---|---|
| implement | Acts as the implementer: follows `ticket-implementer` in its worktree, then stops. The main session dispatches `ticket-verifier`, strips the comments, commits and pushes. The author never grades its own work. |
| review | Fixes the threads in the PR's worktree, then stops. The main session pushes, and posts the replies after the user approves them. |
| verify | Runs `verify-ticket-deployed` and `verify-ticket-behaviour` read-only. It drafts the verdict comment and recommends the transition. |
| promote | Stops at once and reports the ticket as ready to promote. A promote moves services, not tickets, so the main session runs `promote-tickets` once for the whole batch. |
| readiness, refine, triage, unblock | Does the read-only part: the grade, the root cause, the draft Done-when or sub-task. It returns each write as a draft. |

End the run with exactly this report, which is its whole return value:

```text
ticket:        CORE-1234
stage:         implement — implement-ticket step 4
did:           <one line per thing done, with file:line or command>
evidence:      <what it proved, each item with the command or comment it came from>
worktree:      <path> on <branch> at <head sha> (not pushed) | none
needs_agent:   ticket-verifier on <branch>@<sha> | dynamic-env check on PR #N | none
pending:       <one line per write, exact payload: transition id and name,
                comment body file path, commits to push, PR title and body file, sub-task>
questions:     <each question, and who can answer it> | none
waits_on:      main session | user | reviewer | dev deploy | owner <name> | nothing
```

Every draft body goes in a per-ticket file (`<KEY>-comment.md`, `<KEY>-pr.md`) in the
scratchpad, never a generic name. Parallel siblings would overwrite each other.

## Critical gotchas

- **Status alone is not the stage.** `In Review` covers "waiting on a reviewer", "threads
  to fix" and "merged but nobody moved it". A PR merged before anyone moved the ticket
  leaves it in `In Progress`. On 2026-10-20, CORE-5206 sat in `In Progress` a day after
  PR #6128 merged. Read the PR before you choose.
- **Work that isn't pushed is invisible to another machine.** Nothing on the ticket shows
  a local branch. From a different machine, the next session restarts from the last
  pushed head.
- **This skill carries no permissions of its own.** Routing to `implement-ticket` does not
  authorise a push, and routing to `promote-tickets` does not authorise a promote. Each
  stage asks for what it needs.
- **Sub-tasks are their own tickets.** A Production Bug's parent never gets a PR, a
  dynamic env or a testing status. Work each sub-task by its own key.
