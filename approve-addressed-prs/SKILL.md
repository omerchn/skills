---
name: approve-addressed-prs
description: Use when asked to approve addressed PRs, sweep the PRs I reviewed, check whether my review comments were addressed, or run /approve-addressed-prs. Finds every open Orchid-Security PR you reviewed, checks each of your review threads (a claimed fix must exist in pushed code; a reasoned push-back counts as addressed), approves the PRs where every thread is addressed, reports the rest as partially or not addressed, then lets you pick which partially addressed PRs and threads to post a follow-up comment on.
user_invocable: true
allowed-tools: Bash(gh *), Bash(jq *), Read, Agent
---

# Approve Addressed PRs

Batch, hands-off follow-up to your reviews. Unlike `verify-pr-review-replies` (one PR, interactive, checks out the branch), this sweeps all PRs, verifies against GitHub directly, and approves without asking — running the skill *is* the approval.

## 1. Find candidate PRs

```bash
ME=$(gh api user --jq .login)
gh api graphql -f q='org:Orchid-Security is:pr is:open reviewed-by:@me -author:@me' -f query='
query($q:String!){ search(query:$q, type:ISSUE, first:100){ nodes{ ... on PullRequest{
  url number title author{login} headRefOid repository{name owner{login}}
  latestOpinionatedReviews(first:50){ nodes{ author{login} state commit{oid} } }
}}}}'
```

(`gh search prs --reviewed-by` silently returns nothing here — use GraphQL.)

Skip a PR if your entry in `latestOpinionatedReviews` is `APPROVED` (already approved).

## 2. Fetch your threads per PR

```bash
gh api graphql -F owner=<OWNER> -F repo=<REPO> -F pr=<N> -f query='
query($owner:String!,$repo:String!,$pr:Int!){ repository(owner:$owner,name:$repo){ pullRequest(number:$pr){
  reviewThreads(first:100){ nodes{ id isResolved isOutdated path line originalLine
    comments(first:50){ nodes{ author{login} body createdAt originalCommit{oid} } } } }
}}}'
```

Keep threads whose **first** comment author is `$ME`. A PR with zero such threads (e.g. only a "reviewing" placeholder review) goes to the **No comments from you yet** bucket — never approve it.

## 3. Grade each thread

Every thread is exactly one of:

- **Addressed — fix verified**: the author (or anyone but you) claims a fix, or the thread is resolved, **and** the pushed code shows it. Verify against GitHub, no checkout:
  - Diff since your comment: `gh api repos/<OWNER>/<REPO>/compare/<originalCommit.oid>...<headRefOid> --jq '.files[] | select(.filename=="<path>") | .patch'`
  - Current file: `gh api "repos/<OWNER>/<REPO>/contents/<path>?ref=<headRefOid>" --jq .content | base64 -d`, read around `line` (or `originalLine` if outdated).
  - If compare 404s (force-push dropped the anchor), judge from the current file alone and say so.
  - The change must actually resolve what your comment asked for — a touched file or a resolved checkbox is not proof.
- **Addressed — push-back**: the author replied with a reason not to change it (disagreement, out of scope, follow-up ticket). Counts as addressed regardless of whether you agree; quote the reason in the report.
- **Not addressed — fix claimed but missing**: they say "fixed/done" but the code doesn't show it. This is the most important thing to catch.
- **Not addressed — no reply**: no response and no code change that resolves it.
- **Not addressed — vague**: "will look", "good catch", 👍 with no code change.

When unsure between verified and missing, grade it missing and say why.

For more than 3 PRs, grade them in parallel with one `general-purpose` Agent per PR, passing it the PR URL, `$ME`, and this section verbatim; it returns the per-thread grades and must not post anything.

## 4. Act

- **All threads addressed** → approve:
  ```bash
  gh pr review <URL> --approve -b "All my comments are addressed — LGTM."
  ```
  On failure, retry once, then report it and continue.
- Anything else → do not approve, do not reply, do not resolve/unresolve. The only other write is the opt-in follow-up comment in step 6.

## 5. Report

Print three sections, PR link + title + author on each line:

1. **Approved** — PR, `n threads: x fixed, y push-backs`.
2. **Partially addressed** — PR, then one bullet per *unaddressed* thread: `path:line — <grade> — <one-line why>`.
3. **Not addressed at all** — same bullets (every thread unaddressed).

Then one line listing **No comments from you yet** PRs, and any skipped/failed PRs with the reason.

## 6. Follow-up comments (opt-in)

Skip if there are no **Partially addressed** PRs.

1. `AskUserQuestion`, `multiSelect: true`: which partially addressed PRs to comment on. One option per PR (label `repo#N`, description = title + unaddressed count). Max 4 options per question — split into several questions if needed. Picking none ends the skill.
2. For each chosen PR, `AskUserQuestion`, `multiSelect: true`: which unaddressed threads to include. One option per thread (label `path:line`, ≤5 words; description = grade + one-line why). Up to 4 questions per call, 4 options each.
3. For each chosen PR, post **one** review with `--comment` (never approve or request changes):
   ```bash
   gh pr review <URL> --comment -b "<body>"
   ```
   Body: one bullet per selected thread — `` `path:line` `` + what is still missing, worded per grade (no reply → ask for a fix or a reason; fix claimed but missing → say what the pushed code still does; vague → ask for the concrete change). If a thread looks fixed in code but has no reply, say so and ask the author to reply/resolve instead. End with "I'll approve once these are addressed." Keep it short; no restating the original comment.
4. Report which PRs got a comment.
