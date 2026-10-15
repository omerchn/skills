---
name: review-pr
description: Use when asked to review a PR and post comments, or run /review-pr. Takes a PR URL, sizes up the diff's risk/complexity/impact to pick an effort level, challenges the PR's product and architecture decisions (via judge-pr-necessity-and-direction plus a product/architecture checklist), runs the built-in /code-review on that PR at that level, keeps only its blocking (high/medium severity) findings, and lets the user multi-select which ones to post as inline review comments on the PR. Approves the PR when there is nothing to post.
user_invocable: true
allowed-tools: Bash(gh *), Bash(git *), Skill, Agent, AskUserQuestion, Read
---

# Review PR

Run the built-in `/code-review` on a PR, then let the user pick which of its blocking findings get posted as inline comments.

Thin orchestrator. All review work happens in `/code-review`. This skill sizes up the diff to pick an effort level, challenges the product and architecture first, then filters, asks, and posts — or approves when nothing is worth posting.

## Steps

### 1. Resolve the PR

- User passed a URL → extract `OWNER`, `REPO`, `PR_NUMBER`.
- User passed a number → `gh repo view --json nameWithOwner -q .nameWithOwner` for the repo.
- Nothing passed → `gh pr view --json number,url,title -q '{number,url,title}'`.

No PR resolvable → stop: *"No PR found. Pass a PR URL or number."*

Print `#<PR_NUMBER> <title>`.

### 2. Size up the changes

Look at the PR before recommending an effort level:

```bash
gh pr view <PR_NUMBER> --json title,body,files,additions,deletions,changedFiles
gh pr diff <PR_NUMBER>
```

For a large diff, list the files first (`gh pr diff <PR_NUMBER> --name-only` — `gh pr diff` has no `--stat`) and only pull the full diff for the files that matter.

Judge three things:

- **Risk** — auth, permissions, money, migrations, deletes, concurrency, crypto, external input, error handling.
- **Complexity** — new control flow, tricky invariants, async/ordering, wide refactors, subtle data shape changes.
- **Impact** — blast radius: shared/core modules and public APIs beat a leaf component; how many call sites move.

Pick the level:

| Level | When |
|---|---|
| `low` | Small, mechanical, low blast radius — renames, config, copy, generated files, dependency bumps, test-only. |
| `medium` | Ordinary feature or bugfix, contained to a few files, no risky surface. |
| `high` | Any of: risky surface touched, non-trivial new logic, shared/core module, wide refactor, weak test coverage, security/data-integrity/migration paths. |

Never offer or run `max` — too heavy and slow. `high` is the ceiling.

Print two or three lines: what the PR does, and the risk / complexity / impact read that drives the level. Use that level — do not ask the user to confirm it.

### 3. Challenge product and architecture

Before any code review, question whether the PR should exist and whether it is built the right way. **Skip this step when step 2 picked `low`.**

Get the stage: `gh pr view <PR_NUMBER> --json isDraft,reviewDecision`.

Dispatch one `Agent` (`general-purpose`) so its lookups stay out of this context. Prompt it to:

1. Run the `orchid:judge-pr-necessity-and-direction` skill on `<PR_URL>`, with these overrides:
   - The PR's stage is `<draft | in review | approved>` — don't ask.
   - Report only — never post, never ask the user anything.
   - Live measurement (Datadog / Snowflake / flag config) **only at `high`**. At `medium`, use static evidence only: code, git history, ticket, open PRs.
   - `verdict` and `query-unleash-flags` are not installed — do those checks by hand.
2. Then grade each item below **OK** or **CONCERN**, with one line of reasoning. Use **N/A** when the PR doesn't touch that area.

   *Product*
   - **Delivers the ticket** — every case in the ticket/Done-when is handled; nothing is silently dropped.
   - **Scope** — no behaviour nobody asked for.
   - **Consistency** — user-facing changes (API shape, UI, defaults, error messages) match how the product already behaves.

   *Architecture*
   - **Data model** — schema / data-shape changes fit the existing model; migrations are reversible.
   - **Coupling** — no new cross-service coupling and no sync calls added on hot paths.
   - **Consistency & ordering** — no new unstated assumptions about ordering, idempotency, or eventual consistency.
   - **New surface** — no new dependency, pattern, or abstraction where an existing one does the job.
3. Return the skill's report (verdict-first shape), then the checklist, then a list of **concerns**: each with a title, its one-line evidence, and a ready-to-post comment paragraph. Don't invent alternatives — "right direction" and all-OK are normal results.

**Gate.** There is a concern when necessity is not `Required`, direction is `Inertia` or `Right problem, wrong layer`, or any checklist item is CONCERN. (`Right for now, with a named residue` is fine — mention the residue, not a concern.)

- **No concerns** → print the two grades in one line and go to step 4.
- **Concerns** → print the agent's report. Then `AskUserQuestion` with `multiSelect: true` to pick which concerns to post (4 per question, same batching as step 6). Then ask, single-select: **Continue to code review** or **Stop here**.
  - Selected concerns are posted as the **review body** in step 7, one paragraph each, under a `**Product / architecture**` heading.
  - **Stop here** → go straight to step 7 with no inline comments, then step 9.

Any concern posted means the PR is **not** approved in this run.

### 4. Run the review

`Skill` tool, `skill`: `code-review`, `args`: `<effort> <PR_URL>` — **effort first**.

`/code-review` only reads its *first* token as an effort level; anything else there is treated as the target. Passing `<PR_URL> <effort>` silently drops the level and the review falls back to whatever level was last used, with no warning. Confirm the level in the review's own output before trusting it.

**Never pass `--comment` or `--fix`** — this skill posts only what the user selects, and posting happens in step 7.

Capture the full output.

### 5. Filter to blocking findings

`/code-review` returns findings ranked most-severe-first. There is **no fixed section heading** to key on — it reports via `ReportFindings` when that tool is available and as ranked prose when it is not, so filter on the findings themselves:

- **Keep** anything the review labels high or medium severity, or marks `CONFIRMED`.
- **Drop** anything labelled low / nit / optional / style, anything marked `PLAUSIBLE` with hedged wording, and the section listing what the review checked and found correct.

For each kept finding capture: `path`, `line`, `title`, `body` (the finding's explanation, plus its suggested fix if `/code-review` gave one).

Line numbers in the review are not always postable. Before step 7, confirm each `line` is a RIGHT-side line inside the diff — anchor to the nearest added line in the same hunk if it isn't.

Zero kept findings → approve (step 8) — unless step 3 selected concerns, then post them (step 7). Do not ask anything.

### 6. Multi-select

`AskUserQuestion` with `multiSelect: true`. Options are limited to 4 per question and 4 questions per call, so batch findings 4 per question and repeat the call until every finding has been offered. Label each option `<path>:<line> — <title>` (truncate the title to fit), description = one-line summary of the finding.

Nothing selected → approve (step 8) — unless step 3 selected concerns, then post them (step 7).

### 7. Post as one review

Get the head SHA:

```bash
gh pr view <PR_NUMBER> --json headRefOid -q .headRefOid
```

Post all selected findings (and any concerns selected in step 3) as a single COMMENT review — write the JSON to a temp file and pipe it in:

```bash
gh api repos/<OWNER>/<REPO>/pulls/<PR_NUMBER>/reviews --input <file>
```

Body:

```json
{
  "commit_id": "<HEAD_SHA>",
  "event": "COMMENT",
  "body": "<step 3 concerns, or omit when none>",
  "comments": [
    { "path": "src/foo.ts", "line": 42, "side": "RIGHT", "body": "..." }
  ]
}
```

With no inline comments (stopped at step 3, or code review found nothing), send `body` only — omit `comments`.

If the API rejects a comment because the line isn't in the diff, drop that comment, retry the rest, and tell the user which ones were dropped.

Then go to step 9.

### 8. Approve (nothing to post)

```bash
gh pr review <PR_NUMBER> --repo <OWNER>/<REPO> --approve
```

No body. If GitHub refuses (e.g. it's your own PR), report the error and stop — don't retry.

### 9. Report

One line:
- Posted → *"Posted K product/architecture concerns and N of M findings as inline comments on #<PR_NUMBER>: <review URL>."* (drop whichever part is zero)
- Approved → *"Nothing worth posting — approved #<PR_NUMBER>."*

## Rules

- **Only blocking findings** are ever offered. Nits never reach the user.
- **Only selected findings and concerns get posted** — never the whole review. The review body holds selected step 3 concerns and nothing else.
- **One review, not N standalone comments.**
- **Never ask for the effort level** — use the one step 2 picks.
- **Approve only when nothing is posted.** Posting comments and approving never happen in the same run.
- **Never commit, push, or request changes** — a comment review's `event` is always `COMMENT`.
