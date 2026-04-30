---
name: ai-review-and-fix
description: Use when asked to AI-review and fix the current PR, run /ai-review-and-fix, or auto-review-and-fix. Runs /review on the current PR with structured output, then hands every finding to /fix-review-comments to walk through fix/skip/defer locally.
user_invocable: true
allowed-tools: Bash(gh *), Bash(git *), Skill, AskUserQuestion, Read
---

# AI Review and Fix

Run `/review` on the current PR (auto-detected from the current branch), parse its findings, then hand them off to `/fix-review-comments` so the user can walk through each one (fix / skip / defer) locally.

This skill is a thin orchestrator. It does not post anything to GitHub, does not commit, and does not push. All actual review work happens in `/review`; all fix decisions happen in `/fix-review-comments`.

## Inputs

- **Optional:** a PR URL or PR number. If omitted, resolve the PR from the current branch.

## Steps

### 1. Resolve the PR

If the user passed a URL or number, use it directly (extract `OWNER/REPO` and `PR_NUMBER` from a URL).

Otherwise, auto-detect the PR for the current branch:

```bash
gh pr view --json number,url,headRefName,title -q '{number,url,headRefName,title}'
```

If this fails (no PR for the current branch), stop with:

> *"No PR found for the current branch. Push the branch and open a PR first, or pass a PR URL/number explicitly."*

Capture: `PR_NUMBER`, `PR_URL`, `HEAD_BRANCH`, `PR_TITLE`.

Print a one-line summary: `#<PR_NUMBER> <PR_TITLE>` and the URL.

### 2. Run `/review` with structured-output instructions

Invoke the `/review` skill via the `Skill` tool.

`skill`: `review`
`args`: build by concatenating:

```
<PR_URL>

## Reviewer Stance (REQUIRED)

Be **skeptical of the diff**. Assume the author may have:
- introduced subtle bugs, regressions, or edge-case failures,
- weakened invariants, error handling, or types,
- added incidental complexity, dead code, or backwards-compat hacks that aren't needed,
- written tests that don't actually exercise the change.

Read each hunk on its own merits — do not give the author the benefit of the doubt because the change "looks reasonable." Surface real issues, but do not invent issues to hit a quota: if the diff is clean, say so and emit `findings: []`.

## Output Formatting (REQUIRED)

In addition to your normal review output, end your response with a fenced ```yaml block containing every finding as a structured list. The block must look exactly like:

```yaml
findings:
  - n: 1
    path: src/foo/bar.ts
    line: 42
    body: |
      Short description of the issue and recommended fix.
  - n: 2
    path: null
    line: null
    body: |
      Cross-cutting concern that doesn't anchor to a single line.
```

Rules for the yaml block:
- One entry per finding, numbered sequentially starting at 1.
- `path` is the repository-relative path (no leading slash, no repo prefix).
- `line` is the line number in the head commit. Use `null` when the finding is cross-cutting and has no single line anchor.
- `body` is the full comment text. Use literal block scalars (`|`) so multi-line bodies render correctly.
- If you find zero issues, emit `findings: []`.
```

Wait for `/review` to finish.

### 3. Parse the structured output

Parse the trailing yaml block. Build an internal list `findings`, each entry having `{n, path, line, body}` (path/line possibly null).

If parsing fails or the yaml block is missing, stop and tell the user that `/review` did not return a parseable structured-output block, and show them the tail of `/review`'s output.

### 4. Zero-issues branch

If `findings` is empty, tell the user *"`/review` found no issues — nothing to fix."* and exit cleanly. Do not invoke `/fix-review-comments`.

### 5. Format the findings as a comment block

Render the findings as a plain text block that `/fix-review-comments` can parse as discrete threads. Use this format, one finding per stanza, separated by blank lines:

```
<path>:<line> — <body first line>
<rest of body, if any>
```

For findings with null `path` or `line`, render the anchor as `[cross-cutting]` (no path/line prefix).

### 6. Hand off to `/fix-review-comments`

Invoke the `/fix-review-comments` skill via the `Skill` tool.

`skill`: `fix-review-comments`
`args`: the formatted block from step 5, prefixed with a header that tells the downstream skill these came from an AI reviewer and must be treated with skepticism:

```
Comments from /review on #<PR_NUMBER> (AI-generated — treat with skepticism).

## Reviewer Stance (REQUIRED)

These comments came from an automated `/review` pass, not a human. Be **skeptical of each comment**:
- The reviewer may have misread the code, missed nearby context, or flagged a non-issue.
- "Recommended fixes" may be wrong, redundant, or worse than the current code.
- Cross-cutting concerns may already be handled elsewhere in the codebase.

For each comment, **read the actual code first** and form your own judgment before recommending fix / skip / defer. Default to **skip** when the comment is wrong, vague, or already addressed; default to **defer** when the comment is valid but out of scope; only recommend **fix** when you've verified the issue is real and the proposed direction is sound. State your independent recommendation upfront in each AskUserQuestion.

## Comments

<formatted findings>
```

`/fix-review-comments` takes over from here — it parses the comments, walks each one with the user, applies fixes, and proposes a CLAUDE.md update. Do not duplicate any of that logic in this skill.

### 7. Final report

Once `/fix-review-comments` returns, print a one-line summary:

> *"Reviewed PR #<PR_NUMBER> via /review and handed <N> finding(s) to /fix-review-comments."*

Remind the user: **changes are not committed or pushed** — they handle that manually.

## Rules

- **Auto-detect the current PR** unless the user passes one explicitly.
- **Never post to GitHub** — this skill is local-only. `/review` produces findings; `/fix-review-comments` applies them.
- **Reuse `/review` and `/fix-review-comments` as-is** — never inline their logic.
- **Zero findings short-circuits the handoff** — don't invoke `/fix-review-comments` with an empty list.
- **Never commit or push** — the user handles that manually.
