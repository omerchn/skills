---
name: pre-pr-review-and-fix
description: Use before a PR exists, when asked to review my local changes before I open a PR, run code review and fix the findings, pre-PR review, or run /pre-pr-review-and-fix. Scopes the local diff (branch vs origin/main plus uncommitted work, or the working tree on main, with untracked files made visible via intent-to-add), runs the built-in /code-review at high effort as a background fork, then hands its findings to /fix-review-comments to walk through fix/skip/defer locally. For a PR that is already open, use /ai-review-and-fix instead.
user_invocable: true
allowed-tools: Bash(git *), Skill, AskUserQuestion, Read
---

# Pre-PR Review and Fix

Run the built-in `/code-review` at **high** effort on local, not-yet-PR'd changes, then hand its findings to `/fix-review-comments` so the user walks each one (fix / skip / defer) locally.

Thin orchestrator. Review work happens in `/code-review`; fix decisions happen in `/fix-review-comments`. Never inline their logic. Never commit, push, or touch GitHub.

## Steps

### 1. Scope the diff

```bash
git rev-parse --abbrev-ref HEAD
git fetch origin main --quiet
git status --short
```

- **Feature branch** → target is the branch vs `origin/main` plus uncommitted work:
  ```bash
  git log --oneline origin/main..HEAD
  git diff --stat origin/main
  ```
- **On `main`** → target is the working tree: `git diff --stat HEAD`.

Set `REVIEW_TARGET` to one line (`branch <name> vs origin/main + uncommitted` or `working tree on main`) and print it.

**Untracked files are invisible to `git diff`.** From `git status --short`, take every `??` path:

- Clearly part of the change (source, specs, migrations, routes next to tracked edits) → include.
- Relevance unclear (stray notes at the repo root such as `CORE-1234.md`, `*.json` dumps, scratch files) → ask with one `AskUserQuestion` (`multiSelect: true`, batched 4 per question) which to include. Default is to leave them out.

Mark the included ones intent-to-add, by explicit path only:

```bash
git add -N <path> [<path> ...]
```

`-N` records the path with no content, so nothing is staged. **Never `git add -A`, `git add .`, or `git add` without `-N`. Never commit.** Tell the user which paths got intent-to-add (undo with `git reset -- <path>`).

Diff empty after this → stop: *"No local changes to review."*

### 2. Run `/code-review` at high effort

`Skill` tool, `skill`: `code-review` (the built-in, not `code-review:code-review`), `args`: `high`.

- Effort must be the **first** token, or it silently falls back to the last-used level.
- No target arg: with none, `/code-review` reviews the current diff. Never pass `--comment` or `--fix`.

It runs as a **background fork**. Wait for its completion notification. Do not poll, do not re-invoke it, and never predict or fabricate findings while it runs. If the user asks meanwhile, say it is still running.

When it returns, confirm from its output that it ran at `high` and that the files it covered match step 1. If files from step 1 are missing, tell the user which ones before handing off.

### 3. Dedupe against earlier findings

If this conversation already holds findings from an earlier review of the same changes (a prior `/code-review`, `/review`, or pasted review), merge them with the new ones. Drop duplicates, meaning the same file, nearby line and same underlying issue. Keep the more specific wording, and drop any earlier finding that is already fixed in the code.

### 4. Zero findings

No findings → *"`/code-review` (high) found no issues in <REVIEW_TARGET>. Nothing to fix."* Skip to step 6. Do not invoke `/fix-review-comments`.

### 5. Hand off to `/fix-review-comments`

`Skill` tool, `skill`: `fix-review-comments`, `args`: one block holding every finding **verbatim, in the review's severity order** (most severe first):

```
Findings from /code-review (high) on <REVIEW_TARGET>. AI-generated, so treat with skepticism: read the code first, and recommend skip when a finding is wrong or already handled.
Keep this order (severity, most severe first). Do not re-sort by path.

1. [<severity>] <path>:<line> — <summary>
   Failure scenario: <the review's failure scenario / explanation>
   Suggested fix: <if the review gave one>

2. ...
```

Copy each finding's text as the review wrote it. Do not paraphrase, merge, or filter beyond the step 3 dedupe.

### 6. Final

Print the `/fix-review-comments` final report as-is, then one line:

> *"Changes are local and uncommitted. Open the PR when ready (`gh pr create`)."*

Mention any intent-to-add paths from step 1 still in place.

## Rules

- **Local, pre-PR only.** If a PR already exists and the user wants it reviewed, point them to `/ai-review-and-fix`.
- **Always `high` effort**, effort first in `args`.
- **Untracked files reach the review only via `git add -N <explicit paths>`.** Never stage content, never `git add -A`.
- **Wait for the fork's notification.** Never fabricate or predict findings.
- **Findings pass verbatim and in severity order**, deduped against earlier reviews of the same changes.
- **Never commit or push.**
