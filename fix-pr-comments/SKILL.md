---
name: fix-pr-comments
description: Use when asked to fix PR comments, address review feedback, or go through unresolved review threads. Fetches non-resolved inline review threads on the current PR, walks through each one with the user (fix / skip / defer), applies fixes, and replies on GitHub.
user_invocable: true
allowed-tools: Bash(gh *), Bash(git *), Read, Edit, Write, Glob, Grep, AskUserQuestion, TaskCreate, TaskUpdate, TaskList
---

# Fix PR Comments

Walk the user through every non-resolved inline review thread on a PR. For each thread, decide together whether to fix / skip / defer, align on the fix, apply it, reply on GitHub, and resolve the thread.

## Inputs

- **Optional argument:** a PR URL or PR number.
- If not provided, auto-detect from the current branch via `gh pr view`.
- If neither yields a PR, stop and tell the user.

## Steps

### 1. Resolve the PR

- If the user provided a full GitHub PR URL, extract `OWNER/REPO` and `PR_NUMBER`.
- If the user provided just a number, detect the current repo: `gh repo view --json nameWithOwner -q .nameWithOwner`.
- If no argument was given, auto-detect: `gh pr view --json number,url,headRefName,baseRefName`.
- Capture: `PR_NUMBER`, `PR_URL`, `HEAD_BRANCH`, `BASE_BRANCH`.

If no PR is resolvable, stop with: *"No PR found for the current branch. Pass a PR number or URL."*

### 2. Safety check — must be on the PR's head branch

Run `git branch --show-current`. If it does not match `HEAD_BRANCH`:

- **If the user provided a PR URL or number as an argument:** run `gh pr checkout <PR_NUMBER>` to switch to the PR's head branch. If the checkout fails (e.g., dirty working tree), stop and surface the error.
- **If no argument was provided** (PR was auto-detected): stop and tell the user to switch. Do not checkout for them.

Uncommitted changes are fine — proceed regardless. The user handles commits manually.

### 3. Fetch unresolved review threads

Use a GraphQL query to fetch every review thread on the PR. We need `isResolved`, `isOutdated`, `path`, `line`, the thread `id` (for resolving), and each comment's `databaseId` (for REST replies), `author.login`, and `body`.

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
          originalLine
          comments(first:50) {
            nodes {
              databaseId
              author { login }
              body
              createdAt
            }
          }
        }
      }
    }
  }
}' -F owner=<OWNER> -F repo=<REPO> -F pr=<PR_NUMBER>
```

Filter the result to threads where ALL of:
- `isResolved == false`
- `isOutdated == false`

Do not filter by author. Keep self-review threads (PR author commenting on their own PR) and bot comments (e.g., `github-actions[bot]`, any `*-bot` or `[bot]` login).

If zero threads remain, report *"No unresolved review comments found on PR #N — nothing to do."* and exit.

### 4. Sort and create tasks

Sort threads by `path` asc, then `line` asc (nulls last).

Create one task per thread using `TaskCreate` with title `"<path>:<line> — <short body snippet>"`. This gives the user a live progress view.

### 5. Walk each thread

For each thread, in order:

#### 5a. Read the code first

Use `Read` to look at the referenced file around the commented line. Forming a recommendation without reading the code is noise. Skim enough context to judge whether the comment is correct.

#### 5b. Present the thread

Show the user:
- File and line (`path:line`)
- Each comment in the thread in order: `<author>: <body>`
- A one-line read of the code in question

Mark the current task as `in_progress`.

#### 5c. Decide fix / skip / defer

Ask via `AskUserQuestion` with three options, with your recommendation stated upfront in the question text (based on your reading of the code):

- **Fix** — we should address this
- **Skip** — won't fix (invalid / disagreement / no longer applies)
- **Defer** — valid but out of scope for this PR

#### 5d. Act on the decision

Do **not** reply on GitHub or resolve threads during the walk. Only apply local edits and **record the planned reply + resolution** for each thread, keyed by `THREAD_ID` and `FIRST_COMMENT_DATABASE_ID`. All GitHub side effects happen later, in step 7, after the push.

**Fix branch:**
1. Propose a concrete approach in prose, with your recommendation. Wait for the user to agree or adjust.
2. Apply the change using `Edit` (or `Write` for new files). Multi-file fixes are fine — execute whatever scope was agreed.
3. If mid-fix the scope turns out larger than agreed, pause and re-align before continuing.
4. Record the planned reply (`"Addressed — <one-line summary of the change>."`) and that this thread should be **resolved**.
5. Mark the task `completed`.

**Skip branch:**
1. Ask the user briefly: *"Short reason for the reply?"* — one sentence.
2. Record the planned reply (`"Won't fix — <reason>."`) and that this thread should be **resolved**.
3. Mark the task `completed`.

**Defer branch:**
1. Record the planned reply (`"Tracked for follow-up — not addressing in this PR."`) and that this thread should be **left open** (not resolved).
2. Mark the task `completed`.

Never post "Addressed" before the edit is in place — and since all replies are deferred to step 7, never post any reply before the push has succeeded.

### 6. Final report

Summarize:
- PR URL + number
- Counts: fixed / skipped / deferred
- List of files touched (if any)

### 7. Commit, push, then reply and resolve

All GitHub replies and thread resolutions recorded during the walk happen **here**, only after a successful push.

If at least one **Fix** was applied (i.e. there are working-tree changes), ask the user via `AskUserQuestion` whether to:

- Commit and push the fixes, then post replies, resolve threads, and re-request review from human reviewers
- Skip — leave the changes uncommitted

**If the user confirms:**

1. Invoke the `/quick-commit-push` skill to stage, commit, and push the changes.
2. **Only after the push succeeds**, post every recorded reply and resolve every thread marked for resolution:
   - Reply to each thread:
     ```bash
     gh api repos/<OWNER>/<REPO>/pulls/<PR_NUMBER>/comments/<FIRST_COMMENT_DATABASE_ID>/replies \
       -f body="<recorded reply body>"
     ```
   - Resolve each thread marked **resolve** (Fix / Skip) via GraphQL mutation; leave **Defer** threads open:
     ```bash
     gh api graphql -f query='
     mutation($threadId:ID!) {
       resolveReviewThread(input:{threadId:$threadId}) {
         thread { id isResolved }
       }
     }' -F threadId=<THREAD_ID>
     ```
   If the push fails, do **not** post any replies or resolve any threads — surface the error and stop.
3. After replies and resolutions are posted, re-request review from every **human** reviewer who previously reviewed the PR.

   Fetch past reviewers and filter out bots:
   ```bash
   gh api graphql -f query='
   query($owner:String!, $repo:String!, $pr:Int!) {
     repository(owner:$owner, name:$repo) {
       pullRequest(number:$pr) {
         reviews(first:100) {
           nodes {
             author { login __typename }
           }
         }
       }
     }
   }' -F owner=<OWNER> -F repo=<REPO> -F pr=<PR_NUMBER>
   ```

   From the result, collect unique `author.login` values where `__typename == "User"` (excludes `Bot` and `Mannequin`). Also exclude the PR author themselves (`gh pr view <PR_NUMBER> --json author -q .author.login`).

4. Re-request review for each remaining login:
   ```bash
   gh api repos/<OWNER>/<REPO>/pulls/<PR_NUMBER>/requested_reviewers \
     -f reviewers[]=<LOGIN1> -f reviewers[]=<LOGIN2> ...
   ```

5. Report: commit hash, branch pushed, replies posted / threads resolved, and list of reviewers re-requested.

**If the user declines:** remind them the changes are not committed and that no replies were posted or threads resolved — they can handle it manually.

**If no Fix was applied** (nothing in the working tree, only Skips and/or Defers): there is nothing to push, so skip the commit/push prompt. Still post the recorded Skip/Defer replies and resolve the Skip threads (leave Defer threads open) using the same commands as step 2, then report.

## Rules

- **Only inline review threads** — skip issue comments and review summary bodies.
- **Only non-resolved, non-outdated threads.**
- **No author filtering** — include self-review threads and bot comments.
- **Read the code before recommending** fix / skip / defer.
- **Fix / Skip → resolve the thread. Defer → leave open.**
- **Reply and resolve only after push** — during the walk, only apply edits and record planned replies/resolutions; post all replies and resolve all threads in step 7, after the push succeeds. If the push fails, post nothing. (When there are no fixes to push, post the recorded Skip/Defer replies at the end of the walk.)
- **Ask before committing** — never commit/push automatically; always confirm via `AskUserQuestion` at the end.
- **Re-request review from humans only** — filter out bots and the PR author when re-requesting.
