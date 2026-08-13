---
name: review-pr
description: Use when asked to review a PR and post comments, or run /review-pr. Takes a PR URL, asks for an effort level, runs the built-in /code-review on that PR, keeps only the "Worth acting on before merge" findings, and lets the user multi-select which ones to post as inline review comments on the PR.
user_invocable: true
allowed-tools: Bash(gh *), Bash(git *), Skill, AskUserQuestion, Read
---

# Review PR

Run the built-in `/code-review` on a PR, then let the user pick which of its blocking findings get posted as inline comments.

Thin orchestrator. All review work happens in `/code-review`. This skill only chooses the effort level, filters, asks, and posts.

## Steps

### 1. Resolve the PR

- User passed a URL → extract `OWNER`, `REPO`, `PR_NUMBER`.
- User passed a number → `gh repo view --json nameWithOwner -q .nameWithOwner` for the repo.
- Nothing passed → `gh pr view --json number,url,title -q '{number,url,title}'`.

No PR resolvable → stop: *"No PR found. Pass a PR URL or number."*

Print `#<PR_NUMBER> <title>`.

### 2. Ask the effort level

`AskUserQuestion`, header `Effort`, single-select:

- **medium (Recommended)** — balanced; fewer, high-confidence findings
- **low** — quick pass, only the obvious
- **high** — broader coverage, may include uncertain findings
- **max** — exhaustive, slowest

### 3. Run the review

`Skill` tool, `skill`: `code-review`, `args`: `<PR_URL> <effort>`.

**Never pass `--comment` or `--fix`** — this skill posts only what the user selects, and posting happens in step 6.

Capture the full output.

### 4. Filter to blocking findings

Keep only findings under the **"Worth acting on before merge"** heading. Drop everything under nits / optional / already-fine / lower-confidence sections.

For each kept finding capture: `path`, `line`, `title`, `body` (the finding's explanation, plus its suggested fix if `/code-review` gave one).

Zero kept findings → report *"`/code-review` found nothing worth acting on before merge — nothing to post."* and exit. Do not ask anything.

### 5. Multi-select

`AskUserQuestion` with `multiSelect: true`. Options are limited to 4 per question and 4 questions per call, so batch findings 4 per question and repeat the call until every finding has been offered. Label each option `<path>:<line> — <title>` (truncate the title to fit), description = one-line summary of the finding.

Nothing selected → stop, report nothing posted.

### 6. Post as one review

Get the head SHA:

```bash
gh pr view <PR_NUMBER> --json headRefOid -q .headRefOid
```

Post all selected findings as a single COMMENT review — write the JSON to a temp file and pipe it in:

```bash
gh api repos/<OWNER>/<REPO>/pulls/<PR_NUMBER>/reviews --input <file>
```

Body:

```json
{
  "commit_id": "<HEAD_SHA>",
  "event": "COMMENT",
  "comments": [
    { "path": "src/foo.ts", "line": 42, "side": "RIGHT", "body": "..." }
  ]
}
```

If the API rejects a comment because the line isn't in the diff, drop that comment, retry the rest, and tell the user which ones were dropped.

### 7. Report

One line: *"Posted N of M findings as inline comments on #<PR_NUMBER>: <review URL>."*

## Rules

- **Only "Worth acting on before merge" findings** are ever offered. Nits never reach the user.
- **Only selected findings get posted** — never the whole review, never a summary body.
- **One review, not N standalone comments.**
- **Never commit, push, approve, or request changes** — `event` is always `COMMENT`.
