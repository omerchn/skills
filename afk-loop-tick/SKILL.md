---
name: afk-loop-tick
description: Single tick of the AFK agent loop. Picks up unblocked AFK issues, starts implementation workspaces, and checks PR merges. Invoked by the cron or manually via /afk-loop-tick.
user_invocable: true
allowed-tools: mcp__vibe_kanban__list_issues, mcp__vibe_kanban__get_issue, mcp__vibe_kanban__add_issue_tag, mcp__vibe_kanban__remove_issue_tag, mcp__vibe_kanban__list_issue_tags, mcp__vibe_kanban__list_tags, mcp__vibe_kanban__list_repos, mcp__vibe_kanban__list_projects, mcp__vibe_kanban__list_organizations, mcp__vibe_kanban__start_workspace, mcp__github__pull_request_read, mcp__atlassian__getAccessibleAtlassianResources, mcp__atlassian__getJiraIssue, mcp__atlassian__getTransitionsForJiraIssue, mcp__atlassian__transitionJiraIssue, mcp__claude_ai_Atlassian__getAccessibleAtlassianResources, mcp__claude_ai_Atlassian__getJiraIssue, mcp__claude_ai_Atlassian__getTransitionsForJiraIssue, mcp__claude_ai_Atlassian__transitionJiraIssue
---

# AFK Loop Tick

Single tick of the AFK agent loop. Run this manually or let the cron invoke it.

## Constants

- Project name: `Work`
- Worktree repo name: `core-worktrees` (fall back to `core` if not found)
- Branch: `main`
- Max concurrent workspaces: 2

### Tag names (resolved by name at runtime)

- `AFK`
- `in progress`
- `PR`
- `done`

---

## Phase 0: Resolve IDs

Resolve these once at the start of the tick — reuse across both phases.

1. Call `mcp__vibe_kanban__list_organizations` → org ID.
2. Call `mcp__vibe_kanban__list_projects` with the org ID → find the project named `"Work"` (case-insensitive). Store its ID as **WORK_PROJECT_ID**.
3. Call `mcp__vibe_kanban__list_tags` with **WORK_PROJECT_ID** → find tag IDs by name (case-insensitive) for `AFK`, `in progress`, `PR`, `done`. Store as **AFK_TAG_ID**, **IN_PROGRESS_TAG_ID**, **PR_TAG_ID**, **DONE_TAG_ID**.
4. Call `mcp__vibe_kanban__list_repos` → find the repo named `"core-worktrees"` (case-insensitive). If missing, fall back to `"core"`. Store its ID as **WORKTREE_REPO_ID**.

If any of these lookups fails (project/tag/repo not found), abort the tick and report which name could not be resolved.

## Phase 1: Check PR Merges

Run this phase first so that newly-merged blockers are marked "done" before Phase 2 evaluates blocker status.

1. Call `mcp__vibe_kanban__list_issues` with `project_id: WORK_PROJECT_ID`, `status: "Implement"`, `tag_name: "PR"`.

2. For each issue with the "PR" tag:
   a. Fetch the issue with `mcp__vibe_kanban__get_issue`.
   b. Extract the PR URL from the description — look for the pattern `PR: (https://\S+)`.
   c. Parse the PR URL to extract `owner`, `repo`, and `pullNumber` (e.g., from `https://github.com/Orchid-Security/core/pull/456` extract owner=`Orchid-Security`, repo=`core`, pullNumber=`456`).
   d. Call `mcp__github__pull_request_read` with `method: "get"`, `owner`, `repo`, `pullNumber`.
   e. If the PR is merged (check the `merged` field in the response):
      - Add the "done" tag: `mcp__vibe_kanban__add_issue_tag` with `issue_id` and `tag_id: DONE_TAG_ID`.
      - Remove the "PR" tag: call `mcp__vibe_kanban__list_issue_tags` to find the issue-tag relation ID for the "PR" tag, then call `mcp__vibe_kanban__remove_issue_tag` with that `issue_tag_id`.
   f. Otherwise, if the PR is open and **no longer a draft** (check that the `draft` field is `false` and `merged` is `false`), transition the linked Jira issue to **"In Review"**:
      - Extract the Jira URL from the Kanban issue description — look for the pattern `Jira: (https://\S+)`. If none is found, skip this issue.
      - Parse the Jira issue key from the URL (last path segment, e.g., `CORE-1234`).
      - Call `getAccessibleAtlassianResources` → cloudId.
      - Call `getJiraIssue` with the cloudId and Jira key. If the current status name is already `"In Review"` (case-insensitive), skip — no transition needed.
      - Otherwise, call `getTransitionsForJiraIssue` and find the transition whose target status name is `"In Review"` (case-insensitive). Note its transition ID.
      - Call `transitionJiraIssue` with the cloudId, Jira key, and transition ID. If the "In Review" transition is not available from the current state, skip silently.

      Use whichever Atlassian MCP prefix is available in the session (`mcp__atlassian__*` or `mcp__claude_ai_Atlassian__*`). The tool names are identical across both prefixes.

## Phase 2: Pick Up New Work

1. Call `mcp__vibe_kanban__list_issues` with `project_id: WORK_PROJECT_ID`, `status: "Implement"`, `tag_name: "AFK"`.

2. From the results, filter out any issue that has a tag named "done", "in progress", or "PR". Only keep issues that have the "AFK" tag and none of the exclusion tags.

3. Count how many issues currently have the "in progress" tag. Call `mcp__vibe_kanban__list_issues` with `project_id: WORK_PROJECT_ID`, `status: "Implement"`, `tag_name: "in progress"` to get this count. Compute `slots_available = 2 - count`.

4. If `slots_available <= 0`, skip to Reporting.

5. For each candidate issue (up to `slots_available`):
   a. Fetch full issue details with `mcp__vibe_kanban__get_issue` to check relationships.
   b. Check if the issue has any "blocking" relationships where a related issue blocks this one. For each blocking issue, fetch it with `mcp__vibe_kanban__get_issue` and check if it has the "done" tag. If ANY blocker is not done, skip this issue.
   c. If the issue is unblocked:
      - Add the "in progress" tag: `mcp__vibe_kanban__add_issue_tag` with `issue_id` and `tag_id: IN_PROGRESS_TAG_ID`.
      - Start a workspace: `mcp__vibe_kanban__start_workspace` with:
        - `name`: `"AFK Implement: <ISSUE_TITLE>"`
        - `executor`: `"CLAUDE_CODE"`
        - `issue_id`: the issue ID
        - `repositories`: `[{"repo_id": WORKTREE_REPO_ID, "branch": "main"}]`
        - `prompt`: `/kanban-afk-implement`

## Reporting

After both phases, output a brief summary:
- How many AFK issues were found
- How many were eligible (unblocked, no exclusion tags)
- How many workspaces were started
- How many PRs were checked
- How many PRs were merged and marked done
- How many linked Jira issues were transitioned to "In Review"
