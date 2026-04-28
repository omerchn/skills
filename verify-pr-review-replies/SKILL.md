---
name: verify-pr-review-replies
description: Use when asked to verify PR review replies, run /verify-pr-review-replies, or follow up on a PR you reviewed via /start-local-human-pr-review after the author has replied or pushed fixes. Walks your authored review threads one-by-one, verifies "fixed" claims against the code, lets you reply to push-backs (with prettification), nudges or drops silent threads, and resolves/un-resolves accordingly.
user_invocable: true
allowed-tools: Bash(gh *), Bash(git *), Read, Glob, Grep, AskUserQuestion, TaskCreate, TaskUpdate, TaskList
---

# Verify PR Review Replies

Walk every review thread you authored on a PR (resolved or not), classify the author's response, verify "fixed" claims against the code, reply to push-backs, and resolve/un-resolve threads as appropriate.

This is the follow-up to `start-local-human-pr-review`. Run it after the author has had time to reply and/or push fixes.

## Inputs

- **Optional argument:** a PR URL or PR number.
- If not provided, auto-detect from the current branch via `gh pr view --json number,url,headRefName,baseRefName`.
- If neither yields a PR, hard stop with: *"No PR found for the current branch. Pass a PR number or URL."*

## Steps

### 1. Resolve the PR

- If the user provided a full GitHub PR URL, extract `OWNER/REPO` and `PR_NUMBER`.
- If the user provided just a number, detect the current repo: `gh repo view --json nameWithOwner -q .nameWithOwner`.
- If no argument was given, auto-detect from the current branch.
- Capture: `OWNER`, `REPO`, `PR_NUMBER`, `PR_URL`, `HEAD_BRANCH`, `BASE_BRANCH`.

### 2. Hard stop on dirty working tree

```bash
git status --porcelain
```

If output is non-empty, stop with:

> *"Working tree is not clean. Commit, stash, or discard your changes and retry."*

Show the user the porcelain output. Do not stash for them.

### 3. Sync the local branch to the PR head

The whole point of this skill is to verify against the author's latest code, so we must be on the PR's head branch and up-to-date.

1. Run `git branch --show-current`.
2. If the current branch is not `HEAD_BRANCH`, run `gh pr checkout <PR_NUMBER>`.
3. Once on `HEAD_BRANCH`, run `git fetch` then `git pull --ff-only`.
4. If `git pull --ff-only` fails (non-fast-forward — local has diverged from remote), hard stop with:

   > *"Local `<HEAD_BRANCH>` has diverged from remote. Resolve manually (rebase / reset / merge) and retry."*

   Do not attempt to fix the divergence for the user.

After this step, capture `HEAD_SHA = git rev-parse HEAD`.

### 4. Identify the current GitHub user

```bash
gh api user -q .login
```

Capture as `ME_LOGIN`. Used to filter threads to ones you authored.

### 5. Fetch all review threads (resolved + unresolved)

```bash
gh api graphql -f query='
query($owner:String!, $repo:String!, $pr:Int!) {
  repository(owner:$owner, name:$repo) {
    pullRequest(number:$pr) {
      reviewThreads(first:100) {
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          startLine
          originalLine
          originalStartLine
          comments(first:50) {
            nodes {
              databaseId
              author { login }
              body
              createdAt
              originalCommit { oid }
            }
          }
        }
      }
    }
  }
}' -F owner=<OWNER> -F repo=<REPO> -F pr=<PR_NUMBER>
```

Note: pagination beyond 100 threads or 50 comments per thread is not handled. If a real PR exceeds either, surface a warning and continue with what was returned.

### 6. Filter to threads you authored

Keep a thread only if `comments.nodes[0].author.login == ME_LOGIN` (case-insensitive).

Keep both `isResolved == true` and `isResolved == false`. Include `isOutdated` threads — outdated is a strong signal the file changed and is exactly what we need to verify.

If zero threads remain after filtering, print:

> *"No review threads authored by you on PR #N — nothing to verify."*

Exit cleanly. Skip to step 11 (final report) with all-zero counts.

### 7. Classify each thread's status

For each kept thread, determine its `status`:

- **no-reply** — no comments after yours from any author (i.e. `comments.nodes.length == 1`, or all subsequent comments are also yours with no author intervention). Auto-skipped from the verify/push-back flow but still walked for the menu in step 9c.
- **with-reply** — at least one comment after yours from a different author.

For `with-reply` threads, the model proposes a sub-classification by reading the latest non-me reply:
- **claims-fix** — author asserts the issue is addressed (e.g. "fixed", "done in 3a4f12b", "addressed").
- **push-back** — author disagrees, asks for clarification, or replies with no commitment to fix (treat ack-only replies like *"good catch, will look into it"* as push-back).

The model's classification is a proposal only — the user confirms via the menu in step 9b.

### 8. Sort and create tasks

Sort threads by `path` ascending, then `line` ascending (nulls last).

Create one `TaskCreate` per thread with title `"<path>:<line> — <short body snippet>"` so the user has a live progress view.

### 9. Walk each thread

For each thread, in order, mark its task `in_progress` and:

#### 9a. Print thread context

Show:
- File and line (`<path>:<line>`, or `<path>:<startLine>-<line>` for ranges).
- Resolved status (`[resolved]` / `[unresolved]`) and outdated status (`[outdated]` if applicable).
- Each comment in the thread in order: `<author>: <body>`.

#### 9b. Branch on `status`

##### no-reply branch

Print: *"Author has not replied to this comment."*

`AskUserQuestion` with three options:
- **Skip** — no action, advance to next thread.
- **Nudge** — post a fixed reply: `"Gentle ping on this — could you take a look?"`. Do not run prettification on this canned message. Leave thread state unchanged.
- **Drop** — post `"Disregarding this one — never mind."` and resolve the thread. Use this when you re-read your own comment and decide it was wrong.

For Nudge / Drop, the reply API call is:

```bash
gh api repos/<OWNER>/<REPO>/pulls/<PR_NUMBER>/comments/<FIRST_COMMENT_DATABASE_ID>/replies \
  -f body="<message>"
```

For Drop, also resolve via the GraphQL mutation in step 10b.

##### with-reply branch

State the model's classification proposal upfront in the question text, e.g. *"Author claims to have fixed this — verify in code?"* or *"Author is pushing back — what would you like to do?"*.

`AskUserQuestion` with three options:
- **Verify fix** — go to step 9c.
- **Push-back** — go to step 9d.
- **No reply (treat as silent)** — fall through to the no-reply branch.

The user can override the model's read with this menu.

#### 9c. Verify fix flow

Locate the comment's anchor commit:
- Take `comments.nodes[0].originalCommit.oid` (the SHA your comment was anchored to). Capture as `ANCHOR_SHA`.

Generate a diff scoped to the file:

```bash
git diff <ANCHOR_SHA>..HEAD -- <path>
```

If `ANCHOR_SHA` is not reachable in local history (e.g. squash-merge or force-push wiped it), fall back to:

```bash
git diff origin/<BASE_BRANCH>...HEAD -- <path>
```

If `<path>` no longer exists in the working tree (deleted or renamed since the comment), do **not** attempt to follow renames. Instead:

1. Run `git log --diff-filter=D --name-only <ANCHOR_SHA>..HEAD -- <path>` to confirm deletion.
2. Print: *"File `<path>` was deleted or renamed since your review. Cannot auto-verify."*
3. Skip the diff/read step and go straight to the verdict menu below.

If the file does exist, also `Read` it around the commented line region (use line context — at minimum 20 lines around `line`, or the full ranged span plus context).

The model then states a one-line verdict: *"Looks fixed: <brief reason>"* / *"Not fixed: <brief reason>"* / *"Ambiguous: <brief reason>"*.

`AskUserQuestion` with three options:
- **Mark fixed** — post reply `"Confirmed, thanks."` and resolve the thread (or leave resolved if already so). Move on.
- **Push back** — author claimed the fix but you disagree. Drop into the push-back flow (step 9d) with the *same thread*, no re-prompt.
- **Override and resolve** — you want to mark it done without posting a confirmation reply. Just resolve the thread (or leave resolved). No reply posted.

#### 9d. Push-back flow

`AskUserQuestion` with three options:
- **Reply** — go to the reply sub-flow below.
- **Concede** — author has a point. Prompt the user: *"Short reason for the reply?"* (one sentence). Post reply `"Fair point — <reason>."` and resolve the thread.
- **Defer** — no reply, no state change, advance to next thread.

**Reply sub-flow:**

1. Prompt: *"Type your reply. I'll prettify it before posting."*
2. User enters raw reply text.
3. Apply prettification (rules below) to produce `pretty_body`.
4. Show:
   ```
   Raw:    <raw_body>
   Pretty: <pretty_body>
   ```
5. `AskUserQuestion` with three options:
   - **Post** — use `pretty_body` as the reply body.
   - **Edit** — prompt the user (free text) for a verbatim replacement body. **Do not re-prettify.**
   - **Drop** — abort the reply, advance to next thread (no state change).
6. On Post / Edit, send the reply:
   ```bash
   gh api repos/<OWNER>/<REPO>/pulls/<PR_NUMBER>/comments/<FIRST_COMMENT_DATABASE_ID>/replies \
     -f body="<final_body>"
   ```
7. If the thread `isResolved == true` (author resolved before you got here), un-resolve it via:
   ```bash
   gh api graphql -f query='
   mutation($threadId:ID!) {
     unresolveReviewThread(input:{threadId:$threadId}) {
       thread { id isResolved }
     }
   }' -F threadId=<THREAD_ID>
   ```
   Otherwise leave the thread unresolved (you're still arguing).

**Prettification rules** (same as the og skill):
- **Preserve** all technical claims, variable names, function names, file paths, and code snippets verbatim.
- **Never** invent a technical assertion the user didn't make.
- **Fix** typos, grammar, capitalization, hedging fluff ("I think maybe perhaps"), and casing.
- **Restructure** into review-comment style: direct, neutral, 1–3 sentences (unless the user wrote more, in which case keep their length).
- If the user's comment is already well-written, leave it nearly untouched.

After the action completes, mark the task `completed` and advance.

### 10. Reply / resolve API reference

#### 10a. Post a reply on a thread

```bash
gh api repos/<OWNER>/<REPO>/pulls/<PR_NUMBER>/comments/<FIRST_COMMENT_DATABASE_ID>/replies \
  -f body="<text>"
```

`<FIRST_COMMENT_DATABASE_ID>` is `comments.nodes[0].databaseId` from the GraphQL response.

#### 10b. Resolve a thread

```bash
gh api graphql -f query='
mutation($threadId:ID!) {
  resolveReviewThread(input:{threadId:$threadId}) {
    thread { id isResolved }
  }
}' -F threadId=<THREAD_ID>
```

#### 10c. Un-resolve a thread

```bash
gh api graphql -f query='
mutation($threadId:ID!) {
  unresolveReviewThread(input:{threadId:$threadId}) {
    thread { id isResolved }
  }
}' -F threadId=<THREAD_ID>
```

#### 10d. Failure handling

- **5xx or network error:** retry once. If second attempt also fails, print the error, surface what was attempted, and continue to the next thread (do not abort the whole skill).
- **422 / 4xx:** print the response body, surface the offending action, and continue to the next thread. Track failed actions for the final report.
- **Order within a branch:** post reply first, then resolve / un-resolve. Never resolve before the reply lands.

### 11. Final report

Maintain counters as you walk:
- `walked` — total threads visited.
- `verified_fixed` — confirmed fix replies sent + thread resolved.
- `pushed_back` — push-back replies sent (thread left unresolved or un-resolved).
- `conceded` — concession replies sent + thread resolved.
- `nudged` — nudge replies sent.
- `dropped` — disregard replies sent + thread resolved.
- `skipped` — no action taken.
- `failed` — actions that errored.

Also maintain a list `unresolved_threads` of threads where you called the un-resolve mutation.

Print the final report with:
- `PR_URL` and number.
- Only the **non-zero** counters from the list above (zero counts are noise).
- The list of un-resolved threads as `<path>:<line>` bullets, if any. Surface this prominently — GitHub's UI does not make state changes obvious.
- The list of failed actions, if any.
- Branch reminder: *"You're on the PR's head branch (`<HEAD_BRANCH>`). Use `git switch -` to return to your previous branch."*

## Rules

- **Auto-detect first, arg as fallback** — hard stop only if neither yields a PR.
- **Hard stop on dirty tree** — never auto-stash.
- **Sync to PR head with `gh pr checkout` + `git pull --ff-only`** — hard stop on divergence; never reset / clobber for the user.
- **Filter to threads you authored** (first comment) — both resolved and unresolved, including outdated.
- **No 👀 reaction** — author is the one waiting on you, not the other way around.
- **Walk in `path` asc, `line` asc order** — keeps verification spatially anchored.
- **Model classifies, user confirms** — three-button override on every with-reply thread.
- **Verify fix = read diff (`ANCHOR_SHA..HEAD`) + read current file**, with squash fallback to `origin/<base>...HEAD` and a manual fallback when the file no longer exists.
- **Prettification only on free-text replies** — Nudge, Concede, Mark fixed, and Disregard all use canned strings.
- **Edits are verbatim** — no second prettification pass.
- **Reply first, then resolve / un-resolve** — never resolve before the reply lands.
- **Un-resolve any thread the author resolved if you reply with push-back** — keeps the conversation visible.
- **On per-thread API failure, continue to next thread** — surface in the final report; do not abort the whole skill.
- **Stay on the PR branch when done** — do not auto-return.
- **Never commit, push, or modify code** — this skill only reads code and posts replies.
