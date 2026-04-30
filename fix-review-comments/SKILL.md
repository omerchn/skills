---
name: fix-review-comments
description: Use when asked to fix review comments, address feedback, or go through a list of comments the user provides directly (pasted, from a file, or inline). Walks through each comment with the user (fix / skip / defer) and applies fixes locally. Does not touch GitHub or any PR system.
user_invocable: true
allowed-tools: Read, Edit, Write, Glob, Grep, AskUserQuestion, TaskCreate, TaskUpdate, TaskList
---

# Fix Review Comments

Walk the user through a list of review comments they provide directly. For each comment, decide together whether to fix / skip / defer, align on the fix, and apply it locally.

This skill has **no GitHub integration** — it never fetches, replies, or resolves anything remotely. Comments come from the user, fixes stay local.

## Inputs

The user supplies the comments in one of these forms:

1. **Pasted inline** in the conversation (most common — a block of text, a list, or copy-pasted review output).
2. **A file path** to a file containing the comments (e.g. `comments.md`, `review.txt`).
3. **Nothing** — if no comments are provided, ask the user to paste them or point to a file. Do not proceed without input.

## Steps

### 1. Collect the comments

- If the user passed a file path, `Read` it.
- If the user pasted text, use it directly from the conversation.
- If nothing was provided, ask: *"Paste the comments you want to address, or give me a file path."* Wait for input.

### 2. Parse into discrete threads

Split the input into individual comments. Each comment should, where possible, carry:

- **File path** (if mentioned)
- **Line number** (if mentioned)
- **Author** (if mentioned — optional)
- **Body** (the actual feedback)

Comments may be formatted loosely. Use judgment: numbered lists, bullets, `path:line — body` lines, or free-form paragraphs separated by blank lines are all valid. If the structure is ambiguous, show the user how you parsed it and confirm before proceeding.

If only one comment is present, treat it as a single thread — no confirmation needed.

### 3. Sort and create tasks

Sort threads by `path` asc, then `line` asc (nulls last). If no paths are given, preserve the user's original order.

Create one task per thread using `TaskCreate` with title `"<path>:<line> — <short body snippet>"` (or just the snippet if no path/line). This gives the user a live progress view.

### 4. Walk each thread

For each thread, in order:

#### 4a. Read the code first

If the comment references a file (and it exists), `Read` it around the referenced line. Forming a recommendation without reading the code is noise. Skim enough context to judge whether the comment is correct.

If the comment has no file reference, use `Grep`/`Glob` to locate the relevant code based on the comment's content. If you can't find it, say so and ask the user to point you at the file.

#### 4b. Present the thread

Show the user:
- File and line (`path:line`) if known
- The comment body (and author, if provided)
- A one-line read of the code in question (or "couldn't locate" if you couldn't find it)

Mark the current task as `in_progress`.

#### 4c. Decide fix / skip / defer

Ask via `AskUserQuestion` with three options, with your recommendation stated upfront in the question text (based on your reading of the code):

- **Fix** — we should address this
- **Skip** — won't fix (invalid / disagreement / no longer applies)
- **Defer** — valid but out of scope right now

#### 4d. Act on the decision

**Fix branch:**
1. Propose a concrete approach in prose, with your recommendation. Wait for the user to agree or adjust.
2. Apply the change using `Edit` (or `Write` for new files). Multi-file fixes are fine — execute whatever scope was agreed.
3. If mid-fix the scope turns out larger than agreed, pause and re-align before continuing.
4. Mark the task `completed`.

**Skip branch:**
1. Note briefly why (one sentence, for the final report).
2. Mark the task `completed`.

**Defer branch:**
1. Note briefly what's being deferred (one line, for the final report).
2. Mark the task `completed`.

### 5. Final report

Summarize:
- Counts: fixed / skipped / deferred
- List of files touched (if any)
- Brief notes for skipped/deferred items
- Remind the user: **changes are not committed or pushed** — they handle that manually.

## Rules

- **No GitHub / remote calls.** Everything stays local.
- **Read the code before recommending** fix / skip / defer.
- **Edit only after the user agrees** on the approach.
- **Never commit or push** — the user handles that manually.
