---
name: start-local-pr-review
description: Use when asked to review a PR locally, do a local PR review, or run /start-local-pr-review. Checks out the PR in the current repo, fetches Jira context, runs /review, lets the user pick which findings to post, and submits them as a single inline-comment review.
user_invocable: true
allowed-tools: Bash(gh *), Bash(git *), mcp__atlassian__getJiraIssue, mcp__atlassian__searchJiraIssuesUsingJql, mcp__atlassian__getAccessibleAtlassianResources, Skill, AskUserQuestion, Read, Glob, Grep, TaskCreate, TaskUpdate, TaskList
---

# Local PR Review

Check out a PR in the current repo, fetch Jira context, run `/review` with a structured-output instruction, let the user pick which findings to post, and submit them as a single inline-comment review.

## Inputs

- **Required:** a PR URL or PR number. If neither is provided, stop and ask the user for one.

## Steps

### 1. Resolve the PR

- If the user provided a full GitHub PR URL, extract `OWNER/REPO` and `PR_NUMBER` from it.
- If the user provided just a PR number, detect the current repo:
  ```bash
  gh repo view --json nameWithOwner -q .nameWithOwner
  ```

### 2. Hard stop on repo mismatch

If the user provided a URL, compare `OWNER/REPO` from the URL against `gh repo view --json nameWithOwner -q .nameWithOwner` (case-insensitive). If they differ, stop with:

> *"PR is in `<URL_REPO>` but cwd is `<CWD_REPO>`. cd into the right repo and retry."*

Do not attempt to fix this for the user.

### 3. Hard stop on dirty working tree

```bash
git status --porcelain
```

If output is non-empty, stop with:

> *"Working tree is not clean. Commit, stash, or discard your changes and retry."*

Show the user the porcelain output so they can see what needs to be cleaned. Do not stash for them.

### 4. React 👀 on the PR

```bash
gh api repos/<OWNER>/<REPO>/issues/<PR_NUMBER>/reactions -f content=eyes
```

This signals to the PR author that someone is reviewing.

### 5. Fetch PR details

```bash
gh pr view <PR_NUMBER> --repo <OWNER>/<REPO> --json title,author,headRefName,baseRefName,headRefOid,body,url
```

Capture: `PR_TITLE`, `PR_AUTHOR`, `HEAD_BRANCH`, `BASE_BRANCH`, `HEAD_SHA` (`headRefOid`), `PR_BODY`, `PR_URL`.

`HEAD_SHA` is required later for posting inline comments — do not skip it.

### 6. Resolve Jira ticket from branch name

Extract the first match of `[A-Z]+-\d+` from `HEAD_BRANCH`. If found:

1. Call `mcp__atlassian__getAccessibleAtlassianResources` if you don't already have a cloud ID for this session.
2. Call `mcp__atlassian__getJiraIssue` with the cloud ID and ticket key.
3. Capture: `JIRA_KEY`, `JIRA_TITLE`, `JIRA_STATUS`, `JIRA_DESCRIPTION` (first 500 chars), `JIRA_ACCEPTANCE_CRITERIA` if present.

Print a one-line Jira summary to the user: `<KEY> [<STATUS>] <TITLE>`.

If no ticket key matches the regex, set all Jira fields to `"N/A"` and continue.

### 7. Check out the PR locally

```bash
gh pr checkout <PR_NUMBER>
```

This switches to the PR's head branch. Stay on this branch for the rest of the skill — do not return to the previous branch when finished.

### 8. Run `/review` with structured-output instructions

Invoke the `/review` skill via the `Skill` tool. Pass `args` as a single string consisting of the PR URL followed by the structured-output and Jira context blocks below.

`skill`: `review`
`args`: build by concatenating:

```
<PR_URL>

## Jira Ticket Context

- **Ticket:** <JIRA_KEY or "N/A">
- **Title:** <JIRA_TITLE or "N/A">
- **Status:** <JIRA_STATUS or "N/A">
- **Description:** <JIRA_DESCRIPTION or "N/A">
- **Acceptance Criteria:** <JIRA_ACCEPTANCE_CRITERIA or "N/A">

Factor acceptance-criteria deviations into the review.

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
- `body` is the full comment text to post on the PR. Use literal block scalars (`|`) so multi-line bodies render correctly.
- If you find zero issues, emit `findings: []`.
```

Wait for `/review` to finish, then continue with its output in your context.

### 9. Parse `/review`'s structured output

Parse the trailing yaml block. Build an internal list `findings`, each entry having `{n, path, line, body}` with `path` and `line` possibly null.

If parsing fails or the yaml block is missing, stop and tell the user that `/review` did not return a parseable structured-output block, and show them the tail of `/review`'s output so they can see what happened.

### 10. Zero-issues branch

If `findings` is empty:

1. Tell the user: *"`/review` found no issues."*
2. Use `AskUserQuestion` to ask whether to approve the PR (options: **Approve** / **Skip**).
3. If **Approve**:
   ```bash
   gh api repos/<OWNER>/<REPO>/pulls/<PR_NUMBER>/reviews \
     -f event=APPROVE \
     -f body="Reviewed locally — no issues."
   ```
4. If **Skip**: exit cleanly with no posting.

Then go to step 14.

### 11. Present the numbered findings

Print all findings to the user as a numbered list. Show each as:

```
<n>. [<path>:<line>] <first line of body>
    <rest of body, indented>
```

For findings where `line` is null, render the anchor as `[no line — cross-cutting]`.

### 12. Selection prompt

Ask the user (free text, not `AskUserQuestion`):

> *"Enter numbers to post (e.g. `1,3,5-7`), `all`, or `none`."*

Parse the response:
- `none` (case-insensitive) → exit cleanly without posting.
- `all` (case-insensitive) → select every finding.
- Otherwise → parse a comma-separated list of numbers and `start-end` ranges. Reject anything outside `1..len(findings)` with a clear error and re-prompt once.

### 13. Per-comment review pass (post / edit / drop)

For each *selected* finding, in order, use `AskUserQuestion` with three options:

- **Post** — post as-is.
- **Edit** — prompt the user (free text) for a replacement body, then mark this finding as Post with the new body.
- **Drop** — exclude this finding from the posted review.

Before each prompt, show the finding's `path`, `line`, and current body. Track a `to_post` list with the final `{path, line, body}` for each finding marked Post.

### 14. Build and submit the review

Partition `to_post` into:

- `inline_comments`: entries where `path` and `line` are both non-null.
- `body_chunks`: entries where `path` or `line` is null. These get pooled into the review's top-level body, prefixed with `### Cross-cutting` and joined with `\n\n---\n\n` between chunks.

Build the review body:
- If `body_chunks` is empty → empty body.
- Else → `"### Cross-cutting\n\n" + body_chunks.join("\n\n---\n\n")`.

If both `inline_comments` and `body_chunks` are empty (the user dropped everything) → tell the user *"Nothing to post — all findings dropped."* and exit cleanly.

Submit a single review:

```bash
gh api repos/<OWNER>/<REPO>/pulls/<PR_NUMBER>/reviews \
  --method POST \
  -f event=COMMENT \
  -f body="<REVIEW_BODY>" \
  -f commit_id=<HEAD_SHA> \
  -F 'comments[][path]=<path>' \
  -F 'comments[][line]=<line>' \
  -F 'comments[][body]=<body>' \
  -F 'comments[][side]=RIGHT'
```

For multiple inline comments, repeat the `-F 'comments[][path]=…' -F 'comments[][line]=…' -F 'comments[][body]=…' -F 'comments[][side]=RIGHT'` triplets — each set of three forms one comment. `side=RIGHT` anchors against the PR head.

If `inline_comments` is empty but `body_chunks` exists, omit the `comments[]` arguments entirely (a body-only review).

Capture the review URL from the API response.

### 15. Final report

Print:
- PR URL and number.
- Counts: `<X> findings, <Y> selected, <Z> posted, <W> dropped`.
- The submitted review URL (or "approved" / "no review posted" depending on path).
- Reminder: *"You're on the PR's head branch (`<HEAD_BRANCH>`). Use `git switch -` to return to your previous branch."*

## Rules

- **Required argument** — PR URL or number. No auto-detect.
- **Hard stop on repo mismatch** — do not try to switch repos for the user.
- **Hard stop on dirty tree** — never auto-stash.
- **Always 👀 first**, but only after the safety checks pass.
- **Stay on the PR branch when done** — do not auto-return.
- **Reuse `/review`** — never inline a custom review pipeline. Pass Jira context and the structured-output instruction in `args`.
- **Single review with `event=COMMENT`** — never post N individual inline comments.
- **Non-line-anchored findings → top-level body**, never silently dropped.
- **Zero issues → ask before approving** — never auto-approve, never post empty `COMMENT` reviews.
- **Per-comment Post/Edit/Drop** before submission — even after the bulk selection.
- **Never commit, push, or modify code** — this skill only reads code and posts a review.
