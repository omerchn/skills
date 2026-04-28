---
name: start-local-human-pr-review
description: Use when asked to do a local human-driven PR review, run /start-local-human-pr-review, or review a PR yourself (not via /review). Checks out the PR, prints a summary, accepts comments one-by-one from the user, prettifies them, and submits as a single inline-comment review.
user_invocable: true
allowed-tools: Bash(gh *), Bash(git *), mcp__atlassian__getJiraIssue, mcp__atlassian__searchJiraIssuesUsingJql, mcp__atlassian__getAccessibleAtlassianResources, AskUserQuestion, Read, Glob, Grep
---

# Local Human PR Review

Check out a PR, fetch Jira context, print a summary for the human reviewer, accept lazy comments one-by-one, prettify them, and submit as a single inline-comment review.

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

Show the user the porcelain output. Do not stash for them.

### 4. React 👀 on the PR

```bash
gh api repos/<OWNER>/<REPO>/issues/<PR_NUMBER>/reactions -f content=eyes
```

### 5. Fetch PR details

```bash
gh pr view <PR_NUMBER> --repo <OWNER>/<REPO> --json title,author,headRefName,baseRefName,headRefOid,body,url,additions,deletions
```

Capture: `PR_TITLE`, `PR_AUTHOR`, `HEAD_BRANCH`, `BASE_BRANCH`, `HEAD_SHA` (`headRefOid`), `PR_BODY`, `PR_URL`, `TOTAL_ADDITIONS`, `TOTAL_DELETIONS`.

`HEAD_SHA` is required later for posting inline comments — do not skip it.

### 6. Resolve Jira ticket from branch name

Extract the first match of `[A-Z]+-\d+` from `HEAD_BRANCH`. If found:

1. Call `mcp__atlassian__getAccessibleAtlassianResources` if you don't already have a cloud ID for this session.
2. Call `mcp__atlassian__getJiraIssue` with the cloud ID and ticket key.
3. Capture: `JIRA_KEY`, `JIRA_TITLE`, `JIRA_STATUS`, `JIRA_DESCRIPTION` (first 500 chars), `JIRA_ACCEPTANCE_CRITERIA` if present.

If no ticket key matches, set all Jira fields to `"N/A"` and continue.

### 7. Check out the PR locally

```bash
gh pr checkout <PR_NUMBER>
```

Stay on this branch for the rest of the skill — do not return to the previous branch when finished.

### 8. Build the diff-hunk index (strict validation source)

Get the structured file list and patches:

```bash
gh api repos/<OWNER>/<REPO>/pulls/<PR_NUMBER>/files --paginate
```

For each file in the response, capture:
- `filename` (path)
- `status` (added / modified / removed / renamed)
- `additions`, `deletions`
- `patch` (the unified diff for that file — may be missing for binary or oversized files)

Build an internal map `valid_lines: { path → set<int> }` of valid RIGHT-side lines (the only side this skill comments on, since we always use `side=RIGHT`):

For each `patch`:
1. Parse hunk headers `@@ -<oldStart>,<oldCount> +<newStart>,<newCount> @@`.
2. Walk the hunk body. Track a counter `cur` starting at `newStart`.
3. For each line:
   - Starts with `+` → add `cur` to `valid_lines[path]`, then `cur += 1`.
   - Starts with ` ` (context) → add `cur` to `valid_lines[path]`, then `cur += 1`.
   - Starts with `-` → do NOT add, do NOT increment.
4. Files with no `patch` (binary, oversized) get an empty set; comments on them will be rejected.

Also build `files_summary`: ordered list of `{ path, status, additions, deletions }` for the printed summary.

### 9. Print the reviewer summary

Print exactly this structure (markdown):

```
# PR #<N> — <PR_TITLE>
<PR_URL>
Author: <PR_AUTHOR> · Branch: <HEAD_BRANCH> → <BASE_BRANCH>
Churn: +<TOTAL_ADDITIONS>/-<TOTAL_DELETIONS> across <len(files_summary)> files

## Jira
<JIRA_KEY> [<JIRA_STATUS>] <JIRA_TITLE>
<JIRA_DESCRIPTION>
Acceptance criteria: <JIRA_ACCEPTANCE_CRITERIA>

## PR description
<PR_BODY verbatim, or "(empty)" if blank>

## Diff summary (auto)
<bullet summary of what changed; SKIP this section entirely if TOTAL_ADDITIONS + TOTAL_DELETIONS > 2000>
```

For the auto summary: read the patches you already have in memory, group by directory or feature, produce 3–8 bullets. Do not invent things; if the diff is mostly mechanical (renames, type-only), say so. Skip entirely above the 2000-line cap.

Do not print the per-file list in the summary — `files_summary` is only used internally for validation and counts.

### 10. Open the comment loop

After the summary, print:

> *"Type one comment per message:*
> *  • `path:line <body>` — single-line, e.g. `src/foo.ts:42 should use const`*
> *  • `path:start-end <body>` — line range, e.g. `src/foo.ts:42-58 this loop is O(n²)`*
> *  • `cross: <body>` — cross-cutting comment (no file/line anchor)*
> *Type `done` when finished."*

Then enter the loop. Maintain an internal buffer `raw_comments: list[{ path, line, end_line, body }]` where:
- `path` is null for cross-cutting.
- `line` is null for cross-cutting; otherwise an int.
- `end_line` is null for single-line; otherwise an int and `> line`.
- `body` is the user's raw text.

For each user message:

#### 10a. Detect `done`

If the message (trimmed, case-insensitive) is exactly `done`, exit the loop and go to step 11.

#### 10b. Detect cross-cutting

If the message starts with `cross:` (case-insensitive, optionally with whitespace after the colon):
- `path = null`, `line = null`, `end_line = null`.
- `body` = everything after `cross:`.
- If body is empty, error: *"Empty cross-cutting comment. Re-type with body."* and re-prompt without consuming.
- Otherwise append to `raw_comments`, echo `✓ Noted [cross-cutting]`, continue loop.

#### 10c. Parse `path:line[-end] <body>`

Otherwise, parse the first whitespace-delimited token as the anchor:
- Token must contain at least one `:`. Split on the LAST `:` → `path` and `line_spec`.
- `path` must not start with `/` and must not be empty. Strip a leading `./` if present.
- `line_spec` matches one of:
  - `\d+` → `line = int`, `end_line = null`.
  - `\d+-\d+` → `line = int(first)`, `end_line = int(second)`. Require `end_line > line`.
- `body` = the rest of the message after the first whitespace separator. Must be non-empty.

On any parse failure (no colon, bad line spec, empty body, `end_line <= line`), echo a specific error pointing at what failed and re-prompt **without consuming a slot**.

#### 10d. Validate against the diff-hunk index

- If `path` not in `valid_lines`, error: *"`<path>` is not a changed file in this PR. Files in the PR: <first 5 paths…>."* Re-prompt.
- If `line` not in `valid_lines[path]`, error: *"Line <line> in `<path>` is not part of the diff. Nearest valid lines: <up to 5 closest>."* Re-prompt.
- If `end_line` is set and not in `valid_lines[path]`, same error for `end_line`.
- If both `line` and `end_line` set, require both in the same hunk (i.e. valid lines from `line` to `end_line` are contiguous in `valid_lines[path]` — every int in `[line..end_line]` is in the set). Otherwise error: *"Range `<line>-<end_line>` crosses a hunk boundary. Pick a tighter range."* Re-prompt.

On success, append `{ path, line, end_line, body }` to `raw_comments` and echo:
- Single-line: `✓ Noted [<path>:<line>]`
- Range: `✓ Noted [<path>:<line>-<end_line>]`

Then continue the loop.

### 11. Zero-comments branch

If `raw_comments` is empty after `done`:

1. Use `AskUserQuestion` with options **Approve** / **Skip**.
2. If **Approve**:
   ```bash
   gh api repos/<OWNER>/<REPO>/pulls/<PR_NUMBER>/reviews \
     --method POST \
     -f event=APPROVE \
     -f body="Reviewed locally — no issues."
   ```
3. If **Skip**: exit cleanly with no posting.

Then go to step 15.

### 12. Batch prettify

For each entry in `raw_comments`, produce a `pretty_body` field. Prettification rules (medium scope):

- **Preserve** all technical claims, variable names, function names, file paths, and code snippets verbatim.
- **Never** invent a technical assertion the user didn't make. If the user said "this is wrong", do not invent the reason.
- **Fix** typos, grammar, capitalization, hedging fluff ("I think maybe perhaps"), and casing.
- **Restructure** into review-comment style: direct, neutral, 1–3 sentences (unless the user wrote more, in which case keep their length).
- If the user's comment is already well-written, leave it nearly untouched.

Build `pretty_comments: list[{ path, line, end_line, raw_body, pretty_body }]` preserving order.

### 13. Per-comment Post / Edit / Drop pass

For each entry in `pretty_comments`, in order, show:

```
[<n>/<total>] <anchor>
Raw:    <raw_body>
Pretty: <pretty_body>
```

Where `<anchor>` is `<path>:<line>`, `<path>:<line>-<end_line>`, or `[cross-cutting]`.

Use `AskUserQuestion` with three options:
- **Post** — append `{ path, line, end_line, body: pretty_body }` to `to_post`.
- **Edit** — prompt the user (free text) for a replacement body. Append `{ path, line, end_line, body: <user replacement, verbatim> }` to `to_post`. **Do not re-prettify.**
- **Drop** — do not append.

### 14. Build and submit the review

Partition `to_post` into:

- `inline_comments`: entries with non-null `path` and `line`.
- `body_chunks`: entries with null `path` (cross-cutting).

Build the review body:
- If `body_chunks` is empty → empty string.
- Else → `"### Cross-cutting\n\n" + body_chunks.map(c => c.body).join("\n\n---\n\n")`.

If `inline_comments` is empty AND `body_chunks` is empty → tell the user *"Nothing to post — all findings dropped."* and skip to step 15.

Submit a single review:

```bash
gh api repos/<OWNER>/<REPO>/pulls/<PR_NUMBER>/reviews \
  --method POST \
  -f event=COMMENT \
  -f body="<REVIEW_BODY>" \
  -f commit_id=<HEAD_SHA> \
  -F 'comments[][path]=<path>' \
  -F 'comments[][line]=<line>' \
  -F 'comments[][side]=RIGHT' \
  -F 'comments[][body]=<body>'
```

For ranged comments, also pass `-F 'comments[][start_line]=<line>' -F 'comments[][start_side]=RIGHT'` and use `end_line` as the `line` field. For multiple comments, repeat the full `comments[][...]` set per comment.

If `inline_comments` is empty but `body_chunks` exists, omit `comments[]` entirely (body-only review).

#### Failure handling

- **5xx or network error:** retry once. If second attempt also fails, fall through to dump-and-exit (below).
- **422 Unprocessable Entity** (usually a bad line that slipped past validation): parse the response body to identify the offending comment (typically by index). Show the offending entry and use `AskUserQuestion` with options:
  - **Drop offending and retry** — remove that one comment from `to_post`, rebuild payload, retry.
  - **Edit offending and retry** — prompt for a verbatim replacement body (not a new line/path — that requires starting over), retry.
  - **Save and exit** — dump `to_post` as a YAML block to the chat and exit cleanly.

  Loop the salvage prompt until the API returns 2xx or the user chooses Save and exit.
- **Any other error:** print the error, dump `to_post` as a YAML block so the user has a record, and exit.

The dump format:

```yaml
unsubmitted:
  - path: src/foo.ts
    line: 42
    end_line: null
    body: |
      <body>
  - ...
```

Capture the review URL from the successful API response.

### 15. Final report

Print:
- PR URL and number.
- Counts: `<X> typed, <Y> dropped, <Z> posted`.
- The submitted review URL (or "approved" / "no review posted" depending on path).
- Reminder: *"You're on the PR's head branch (`<HEAD_BRANCH>`). Use `git switch -` to return to your previous branch."*

## Rules

- **Required argument** — PR URL or number. No auto-detect.
- **Hard stop on repo mismatch** — do not try to switch repos for the user.
- **Hard stop on dirty tree** — never auto-stash.
- **Always 👀 first**, but only after the safety checks pass.
- **Stay on the PR branch when done** — do not auto-return.
- **Strict validation against the diff-hunk index** — never let a parse failure or invalid anchor consume a comment slot.
- **Echo confirmation per comment**, prettify in a single batch after `done`.
- **Medium prettification only** — never invent technical claims.
- **Edits are verbatim** — no second prettification pass.
- **Per-comment Post/Edit/Drop** before submission.
- **Single review with `event=COMMENT`** (or `APPROVE` for the zero-comments path) — never post N individual inline comments.
- **Cross-cutting comments → top-level body**, never silently dropped.
- **On submission failure, salvage rather than lose work** — retry transient errors, surface 422 offenders, dump YAML on terminal failure.
- **Never commit, push, or modify code** — this skill only reads code and posts a review.
