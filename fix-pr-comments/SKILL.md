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

**Fix branch:**
1. Propose a concrete approach in prose, with your recommendation. Wait for the user to agree or adjust.
2. Apply the change using `Edit` (or `Write` for new files). Multi-file fixes are fine — execute whatever scope was agreed.
3. If mid-fix the scope turns out larger than agreed, pause and re-align before continuing.
4. Reply on GitHub to the thread:
   ```bash
   gh api repos/<OWNER>/<REPO>/pulls/<PR_NUMBER>/comments/<FIRST_COMMENT_DATABASE_ID>/replies \
     -f body="Addressed — <one-line summary of the change>."
   ```
5. Resolve the thread via GraphQL mutation:
   ```bash
   gh api graphql -f query='
   mutation($threadId:ID!) {
     resolveReviewThread(input:{threadId:$threadId}) {
       thread { id isResolved }
     }
   }' -F threadId=<THREAD_ID>
   ```
6. Mark the task `completed`.

**Skip branch:**
1. Ask the user briefly: *"Short reason for the reply?"* — one sentence.
2. Reply on GitHub:
   ```bash
   gh api repos/<OWNER>/<REPO>/pulls/<PR_NUMBER>/comments/<FIRST_COMMENT_DATABASE_ID>/replies \
     -f body="Won't fix — <reason>."
   ```
3. Resolve the thread (same GraphQL mutation as above).
4. Mark the task `completed`.

**Defer branch:**
1. Reply on GitHub:
   ```bash
   gh api repos/<OWNER>/<REPO>/pulls/<PR_NUMBER>/comments/<FIRST_COMMENT_DATABASE_ID>/replies \
     -f body="Tracked for follow-up — not addressing in this PR."
   ```
2. Do **not** resolve the thread — leave it open.
3. Mark the task `completed`.

Order within every branch: **edit first (if applicable), then reply, then resolve.** Never post "Addressed" before the edit is in place.

### 6. Final report

Summarize:
- PR URL + number
- Counts: fixed / skipped / deferred
- List of files touched (if any)
- Remind the user: **changes are not committed or pushed** — they handle that manually.

## Rules

- **Only inline review threads** — skip issue comments and review summary bodies.
- **Only non-resolved, non-outdated threads.**
- **No author filtering** — include self-review threads and bot comments.
- **Read the code before recommending** fix / skip / defer.
- **Fix / Skip → resolve the thread. Defer → leave open.**
- **Edit first, then reply, then resolve** — never post "Addressed" before the edit.
- **Never commit or push** — the user handles that manually.
