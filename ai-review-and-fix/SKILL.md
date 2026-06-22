---
name: ai-review-and-fix
description: Use when asked to AI-review and fix the current PR, run /ai-review-and-fix, or auto-review-and-fix. Runs /review on the current PR, then hands the findings to /fix-review-comments to walk through fix/skip/defer locally. Falls back to reviewing local changes (working tree when on main, or branch-vs-main diff otherwise) when no PR exists.
user_invocable: true
allowed-tools: Bash(gh *), Bash(git *), Skill, AskUserQuestion, Read
---

# AI Review and Fix

Run `/review` on the current PR (auto-detected from the current branch) — or on local changes when there's no PR — then hand its findings to `/fix-review-comments` so the user can walk through each one (fix / skip / defer) locally.

This skill is a thin orchestrator. It does not post anything to GitHub, does not commit, and does not push. All actual review work happens in `/review`; all fix decisions happen in `/fix-review-comments`.

## Inputs

- **Optional:** a PR URL or PR number. If omitted, resolve the PR from the current branch; if there's no PR, fall back to reviewing local changes.

## Steps

### 1. Resolve what to review

If the user passed a URL or number, use it directly (extract `OWNER/REPO` and `PR_NUMBER` from a URL) → **PR mode**.

Otherwise, auto-detect the PR for the current branch:

```bash
gh pr view --json number,url,headRefName,title -q '{number,url,headRefName,title}'
```

- **If a PR is found → PR mode.** Capture `PR_NUMBER`, `PR_URL`, `HEAD_BRANCH`, `PR_TITLE`. Print a one-line summary: `#<PR_NUMBER> <PR_TITLE>` and the URL.
- **If no PR is found → local mode** (review local changes instead of stopping).

#### Local mode

Detect the current branch:

```bash
git rev-parse --abbrev-ref HEAD
```

- **On `main` (the default branch):** review the working-tree changes — staged, unstaged, and untracked.

  ```bash
  git status --short
  git diff HEAD
  ```

- **On any other branch:** review the diff of this branch against `main`.

  ```bash
  git diff main...HEAD
  ```

Capture the diff output as `REVIEW_DIFF` and set `REVIEW_TARGET` to a one-line description of what's being reviewed (e.g. `working-tree changes on main` or `branch <name> vs main`). Print `REVIEW_TARGET`.

If `REVIEW_DIFF` is empty (no changes), stop with:

> *"No PR found, and no local changes to review."*

### 2. Run `/review`

Invoke the `/review` skill via the `Skill` tool.

`skill`: `review`
`args`: build by concatenating the review target with the skeptical-stance prefix below.

- **PR mode:** lead with `<PR_URL>`.
- **Local mode:** lead with an instruction and the captured diff, so `/review` has the changes to review without a PR:

  ```
  Review the local changes below — there is no PR. Target: <REVIEW_TARGET>.

  ```diff
  <REVIEW_DIFF>
  ```
  ```

Then append the stance block:

```
## Reviewer Stance (REQUIRED)

Be **skeptical of the diff**. Assume the author may have:
- introduced subtle bugs, regressions, or edge-case failures,
- weakened invariants, error handling, or types,
- added incidental complexity, dead code, or backwards-compat hacks that aren't needed,
- written tests that don't actually exercise the change.

Read each hunk on its own merits — do not give the author the benefit of the doubt because the change "looks reasonable." Surface real issues, but do not invent issues to hit a quota: if the diff is clean, say so explicitly.
```

Wait for `/review` to finish. Capture its full output.

### 3. Zero-issues check

If `/review`'s output indicates no findings (e.g. it explicitly says the diff is clean, no issues, LGTM, etc.), tell the user *"`/review` found no issues — nothing to fix."* and exit cleanly. Do not invoke `/fix-review-comments`.

### 4. Hand off to `/fix-review-comments`

Invoke the `/fix-review-comments` skill via the `Skill` tool.

`skill`: `fix-review-comments`
`args`: `/review`'s full output, prefixed with a header that tells the downstream skill these came from an AI reviewer and must be treated with skepticism:

```
Comments from /review on <#<PR_NUMBER> in PR mode, or <REVIEW_TARGET> in local mode> (AI-generated — treat with skepticism).

## Reviewer Stance (REQUIRED)

These comments came from an automated `/review` pass, not a human. Be **skeptical of each comment**:
- The reviewer may have misread the code, missed nearby context, or flagged a non-issue.
- "Recommended fixes" may be wrong, redundant, or worse than the current code.
- Cross-cutting concerns may already be handled elsewhere in the codebase.

For each comment, **read the actual code first** and form your own judgment before recommending fix / skip / defer. Default to **skip** when the comment is wrong, vague, or already addressed; default to **defer** when the comment is valid but out of scope; only recommend **fix** when you've verified the issue is real and the proposed direction is sound. State your independent recommendation upfront in each AskUserQuestion.

## Comments

<full /review output>
```

`/fix-review-comments` parses loose formats — it can handle `/review`'s natural output directly. It walks each finding with the user, applies fixes, and proposes a CLAUDE.md update. Do not duplicate any of that logic in this skill.

### 5. Final report

Once `/fix-review-comments` returns, print a one-line summary:

> *"Reviewed <PR #<PR_NUMBER> | <REVIEW_TARGET>> via /review and handed off to /fix-review-comments."*

Remind the user: **changes are not committed or pushed** — they handle that manually.

## Rules

- **Auto-detect the current PR** unless the user passes one explicitly. **No PR → review local changes** (working tree on `main`, else branch-vs-`main` diff); only stop when there are no local changes either.
- **Never post to GitHub** — this skill is local-only. `/review` produces findings; `/fix-review-comments` applies them.
- **Reuse `/review` and `/fix-review-comments` as-is** — never inline their logic.
- **Do not impose structured output on `/review`** — pass its natural output through to `/fix-review-comments`, which already handles loose formats.
- **Zero findings short-circuits the handoff** — don't invoke `/fix-review-comments` when `/review` reports a clean diff.
- **Never commit or push** — the user handles that manually.
