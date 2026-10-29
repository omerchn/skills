---
name: fix-pr-conflicts
description: Use when asked to fix PR conflicts, resolve merge conflicts on a PR, update a PR with main, or run /fix-pr-conflicts. Merges the PR's base into its head branch, resolves conflicts via /merge-conflict-resolver, pushes the merge commit, then re-requests review (and pings on Slack) every reviewer whose approval was dismissed by the new push.
user_invocable: true
allowed-tools: Bash(gh *), Bash(git *), Read, Edit, Write, Glob, Grep, AskUserQuestion, Skill, TaskCreate, TaskUpdate, TaskList, mcp__claude_ai_Slack__slack_search_users, mcp__claude_ai_Slack__slack_send_message
---

# Fix PR Conflicts

Bring a PR up to date with its base, resolve conflicts, push the merge commit, and get dismissed reviewers back on it. Review threads are out of scope — that's `/fix-pr-comments`.

## Inputs

- **Optional argument:** a PR URL or number. Otherwise auto-detect with `gh pr view --json number,url,headRefName,baseRefName`.
- No PR resolvable → stop: *"No PR found for the current branch. Pass a PR number or URL."*

## Steps

### 1. Resolve the PR and branch

Same rules as `/fix-pr-comments` steps 1–2: capture `OWNER/REPO`, `PR_NUMBER`, `PR_URL`, `HEAD_BRANCH`, `BASE_BRANCH`. If an argument was given and you're not on `HEAD_BRANCH`, `gh pr checkout <PR_NUMBER>`; if auto-detected, you're already on it.

**Working tree must be clean** (`git status --porcelain` ignoring untracked files). A merge on top of uncommitted edits mixes them into the merge commit — stop and ask the user to commit or stash.

### 2. Merge the base

```bash
git fetch origin <BASE_BRANCH> <HEAD_BRANCH>
git pull --ff-only origin <HEAD_BRANCH>
git merge origin/<BASE_BRANCH> --no-edit
```

- Merge, never rebase — rebasing rewrites reviewed commits and needs a force push.
- `Already up to date.` → nothing to push, no reviews dismissed; report and stop.
- Conflicts → invoke `/merge-conflict-resolver` and follow it until every file is resolved and staged, then `git commit --no-edit`.

### 3. Verify and push the merge commit

Run the scoped checks on the merged tree before pushing (affected projects only):

```bash
NX_BASE=origin/<BASE_BRANCH> pnpm run tsc:affected && NX_BASE=origin/<BASE_BRANCH> pnpm run lint:affected
```

A failure caused by the merge (e.g. an API that changed on the base) is part of resolving the conflict — fix it, `git commit --amend --no-edit` on the merge commit, re-run. A failure that also exists on the base is not yours: note it for the report and push anyway.

```bash
git push --no-verify origin <HEAD_BRANCH>
```

Push failure → stop and surface it. Nothing below runs.

### 4. Re-request dismissed reviewers

The merge push dismisses stale approvals. Fetch each reviewer's latest review:

```bash
gh api graphql -f query='
query($owner:String!, $repo:String!, $pr:Int!) {
  repository(owner:$owner, name:$repo) {
    pullRequest(number:$pr) {
      author { login }
      latestReviews(first:100) { nodes { state author { login __typename } } }
    }
  }
}' -F owner=<OWNER> -F repo=<REPO> -F pr=<PR_NUMBER>
```

Keep logins where `state == "DISMISSED"`, `__typename == "User"`, and not the PR author. For those:

1. Re-request:
   ```bash
   gh api repos/<OWNER>/<REPO>/pulls/<PR_NUMBER>/requested_reviewers -f reviewers[]=<LOGIN1> -f reviewers[]=<LOGIN2>
   ```
2. Slack DM each, exactly as `/fix-pr-comments` does: find them with `slack_search_users` (GitHub login, then real name from `gh api users/<LOGIN> -q .name`) and send `:re-re: ? <PR_URL>`. No match → say so, don't guess.

### 5. Report

Merge commit hash (or "already up to date"), files that conflicted, checks run and any pre-existing failures, and who was re-requested/pinged for a dismissed review.

## Rules

- **Merge, don't rebase; never force-push.**
- **Clean tree before merging.**
- **Never push before conflicts are fully resolved and staged** — no `<<<<<<<` markers (`git diff --check` before committing).
- **Push with `--no-verify`** after running the scoped checks yourself.
- **Never ask to commit or push** once conflicts are resolved; the user invoked the skill to get it done.
