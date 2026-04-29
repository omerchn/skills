---
name: afk-loop-tick
description: Single tick of the AFK agent loop. Picks up unblocked AFK issues, starts implementation workspaces, and checks PR merges. Invoked by the cron or manually via /afk-loop-tick.
user_invocable: true
allowed-tools: mcp__vibe_kanban__list_issues, mcp__vibe_kanban__get_issue, mcp__vibe_kanban__add_issue_tag, mcp__vibe_kanban__remove_issue_tag, mcp__vibe_kanban__list_issue_tags, mcp__vibe_kanban__list_tags, mcp__vibe_kanban__start_workspace, mcp__github__pull_request_read
---

# AFK Loop Tick

Single tick of the AFK agent loop. Run this manually or let the cron invoke it.

## Constants

- Project ID: `c7185330-ce37-4902-bb66-60d6a69b01b5`
- Repo ID (core-worktrees): `f1819923-d554-4f4b-a344-6607d6912c59`
- Branch: `main`
- Max concurrent workspaces: 2

### Tag IDs
- AFK: `7346f2bc-fe58-4e42-b70c-1006f5a51737`
- in progress: `c7f38675-7ed6-4067-aed2-26b6173e265d`
- PR: `b57daa22-1068-44ab-a41f-84793e247af6`
- done: `24bb3bc0-1442-4f51-b2a7-8ff8a09adce0`

---

## Phase 1: Check PR Merges

Run this phase first so that newly-merged blockers are marked "done" before Phase 2 evaluates blocker status.

1. Call `mcp__vibe_kanban__list_issues` with `project_id: "c7185330-ce37-4902-bb66-60d6a69b01b5"`, `status: "Implement"`, `tag_name: "PR"`.

2. For each issue with the "PR" tag:
   a. Fetch the issue with `mcp__vibe_kanban__get_issue`.
   b. Extract the PR URL from the description — look for the pattern `PR: (https://\S+)`.
   c. Parse the PR URL to extract `owner`, `repo`, and `pullNumber` (e.g., from `https://github.com/Orchid-Security/core/pull/456` extract owner=`Orchid-Security`, repo=`core`, pullNumber=`456`).
   d. Call `mcp__github__pull_request_read` with `method: "get"`, `owner`, `repo`, `pullNumber`.
   e. If the PR is merged (check the `merged` field in the response):
      - Add the "done" tag: `mcp__vibe_kanban__add_issue_tag` with `issue_id` and `tag_id: "24bb3bc0-1442-4f51-b2a7-8ff8a09adce0"`.
      - Remove the "PR" tag: call `mcp__vibe_kanban__list_issue_tags` to find the issue-tag relation ID for the "PR" tag, then call `mcp__vibe_kanban__remove_issue_tag` with that `issue_tag_id`.

## Phase 2: Pick Up New Work

1. Call `mcp__vibe_kanban__list_issues` with `project_id: "c7185330-ce37-4902-bb66-60d6a69b01b5"`, `status: "Implement"`, `tag_name: "AFK"`.

2. From the results, filter out any issue that has a tag named "done", "in progress", or "PR". Only keep issues that have the "AFK" tag and none of the exclusion tags.

3. Count how many issues currently have the "in progress" tag. Call `mcp__vibe_kanban__list_issues` with `project_id: "c7185330-ce37-4902-bb66-60d6a69b01b5"`, `status: "Implement"`, `tag_name: "in progress"` to get this count. Compute `slots_available = 2 - count`.

4. If `slots_available <= 0`, skip to Reporting.

5. For each candidate issue (up to `slots_available`):
   a. Fetch full issue details with `mcp__vibe_kanban__get_issue` to check relationships.
   b. Check if the issue has any "blocking" relationships where a related issue blocks this one. For each blocking issue, fetch it with `mcp__vibe_kanban__get_issue` and check if it has the "done" tag. If ANY blocker is not done, skip this issue.
   c. If the issue is unblocked:
      - Add the "in progress" tag: `mcp__vibe_kanban__add_issue_tag` with `issue_id` and `tag_id: "c7f38675-7ed6-4067-aed2-26b6173e265d"`.
      - Start a workspace: `mcp__vibe_kanban__start_workspace` with:
        - `name`: `"AFK Implement: <ISSUE_TITLE>"`
        - `executor`: `"CLAUDE_CODE"`
        - `issue_id`: the issue ID
        - `repositories`: `[{"repo_id": "f1819923-d554-4f4b-a344-6607d6912c59", "branch": "main"}]`
        - `prompt`: `/kanban-afk-implement`

## Reporting

After both phases, output a brief summary:
- How many AFK issues were found
- How many were eligible (unblocked, no exclusion tags)
- How many workspaces were started
- How many PRs were checked
- How many PRs were merged and marked done
