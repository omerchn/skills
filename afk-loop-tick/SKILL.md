---
name: afk-loop-tick
description: Single tick of the AFK agent loop. Picks up unblocked Implement issues (AFK by default — anything without a HITL tag), starts implementation workspaces, syncs draft/open PR tags with GitHub state, and marks merged PRs done. Invoked by the cron or manually via /afk-loop-tick.
user_invocable: true
allowed-tools: mcp__vibe_kanban__list_issues, mcp__vibe_kanban__get_issue, mcp__vibe_kanban__add_issue_tag, mcp__vibe_kanban__remove_issue_tag, mcp__vibe_kanban__list_issue_tags, mcp__vibe_kanban__list_tags, mcp__vibe_kanban__list_repos, mcp__vibe_kanban__list_projects, mcp__vibe_kanban__list_organizations, mcp__vibe_kanban__start_workspace, mcp__github__pull_request_read, mcp__atlassian__getAccessibleAtlassianResources, mcp__atlassian__getJiraIssue, mcp__atlassian__getTransitionsForJiraIssue, mcp__atlassian__transitionJiraIssue, mcp__claude_ai_Atlassian__getAccessibleAtlassianResources, mcp__claude_ai_Atlassian__getJiraIssue, mcp__claude_ai_Atlassian__getTransitionsForJiraIssue, mcp__claude_ai_Atlassian__transitionJiraIssue
---

# AFK Loop Tick

Single tick of the AFK agent loop. Run this manually or let the cron invoke it.

## Tag model

- **AFK is implicit.** Any issue in the `Implement` column without a `HITL` tag is treated as AFK and eligible for autonomous pickup.
- **`draft` and `open`** track the live state of the linked PR. They replace the old single `PR` tag and must stay in sync with GitHub:
  - PR is draft → issue has `draft` (and not `open`)
  - PR is open / ready for review → issue has `open` (and not `draft`)
  - PR is merged → issue has `done` (and neither `draft` nor `open`)

## Constants

- Project name: `Work`
- Worktree repo name: `core-worktrees` (fall back to `core` if not found)
- Branch: `main`
- Max concurrent workspaces: 2

### Tag names (resolved by name at runtime)

- `HITL`
- `in progress`
- `draft`
- `open`
- `done`

---

## Phase 0: Resolve IDs

Resolve these once at the start of the tick — reuse across both phases.

1. Call `mcp__vibe_kanban__list_organizations` → org ID.
2. Call `mcp__vibe_kanban__list_projects` with the org ID → find the project named `"Work"` (case-insensitive). Store its ID as **WORK_PROJECT_ID**.
3. Call `mcp__vibe_kanban__list_tags` with **WORK_PROJECT_ID** → find tag IDs by name (case-insensitive) for `HITL`, `in progress`, `draft`, `open`, `done`. Store as **HITL_TAG_ID**, **IN_PROGRESS_TAG_ID**, **DRAFT_TAG_ID**, **OPEN_TAG_ID**, **DONE_TAG_ID**.
4. Call `mcp__vibe_kanban__list_repos` → find the repo named `"core-worktrees"` (case-insensitive). If missing, fall back to `"core"`. Store its ID as **WORKTREE_REPO_ID**.

If any of these lookups fails (project/tag/repo not found), abort the tick and report which name could not be resolved.

## Phase 1: Sync PR State (draft / open / merged)

Run this phase first so that newly-merged blockers are marked "done" before Phase 2 evaluates blocker status, and so that draft→open transitions are reflected before reporting.

1. Gather all issues with a live PR. Call `mcp__vibe_kanban__list_issues` twice with `project_id: WORK_PROJECT_ID`, `status: "Implement"`:
   - once with `tag_name: "draft"`
   - once with `tag_name: "open"`

   Union the two result sets, deduplicating by issue ID. (An issue should normally have exactly one of these tags, but tolerate both being present and let this phase reconcile.)

2. For each issue in the union:
   a. Fetch the issue with `mcp__vibe_kanban__get_issue`.
   b. Extract the PR URL from the description — look for the pattern `PR: (https://\S+)`. If no PR URL is found, skip the issue and continue.
   c. Parse the PR URL to extract `owner`, `repo`, and `pullNumber` (e.g., from `https://github.com/Orchid-Security/core/pull/456` extract owner=`Orchid-Security`, repo=`core`, pullNumber=`456`).
   d. Call `mcp__github__pull_request_read` with `method: "get"`, `owner`, `repo`, `pullNumber`.
   e. Inspect the PR's `merged` and `draft` fields and reconcile the issue's tags:
      - **If `merged` is true:** add the `done` tag and remove both `draft` and `open` tags (if present).
      - **Else if `draft` is true:** ensure the issue has the `draft` tag and not the `open` tag.
      - **Else (PR is open and not draft):** ensure the issue has the `open` tag and not the `draft` tag. This is the draft → open transition: also transition the linked Jira issue to `"In Review"` (see step f).

      To add a tag, call `mcp__vibe_kanban__add_issue_tag` with `issue_id` and the relevant `tag_id`. To remove a tag, call `mcp__vibe_kanban__list_issue_tags` to find its `issue_tag_id`, then `mcp__vibe_kanban__remove_issue_tag`. Skip add/remove calls when the tag is already in the desired state.

   f. **Jira "In Review" transition** — only when the issue just moved from `draft` to `open` in step e (i.e., the PR is open + not draft AND the issue had the `draft` tag prior to this tick):
      - Extract the Jira URL from the Kanban issue description — look for the pattern `Jira: (https://\S+)`. If none is found, skip.
      - Parse the Jira issue key from the URL (last path segment, e.g., `CORE-1234`).
      - Call `getAccessibleAtlassianResources` → cloudId.
      - Call `getJiraIssue` with the cloudId and Jira key. If the current status name is already `"In Review"` (case-insensitive), skip.
      - Otherwise, call `getTransitionsForJiraIssue` and find the transition whose target status name is `"In Review"` (case-insensitive).
      - Call `transitionJiraIssue` with the cloudId, Jira key, and transition ID. If the transition is not available from the current state, skip silently.

      Use whichever Atlassian MCP prefix is available in the session (`mcp__atlassian__*` or `mcp__claude_ai_Atlassian__*`). The tool names are identical across both prefixes.

## Phase 2: Pick Up New Work

AFK is now the default for the Implement column — there is no `AFK` tag to filter on. Any Implement issue without one of the exclusion tags below is eligible.

1. Call `mcp__vibe_kanban__list_issues` with `project_id: WORK_PROJECT_ID`, `status: "Implement"` (no tag filter — we need to inspect tags client-side).

2. Filter out any issue that has any of these tags: `HITL`, `done`, `in progress`, `draft`, `open`. The remaining issues are AFK candidates.

3. Count how many issues currently have the `in progress` tag. Call `mcp__vibe_kanban__list_issues` with `project_id: WORK_PROJECT_ID`, `status: "Implement"`, `tag_name: "in progress"` to get this count. Compute `slots_available = 2 - count`.

4. If `slots_available <= 0`, skip to Reporting.

5. For each candidate issue (up to `slots_available`):
   a. Fetch full issue details with `mcp__vibe_kanban__get_issue` to check relationships.
   b. Check if the issue has any "blocking" relationships where a related issue blocks this one. For each blocking issue, fetch it with `mcp__vibe_kanban__get_issue` and check if it has the `done` tag. If ANY blocker is not done, skip this issue.
   c. If the issue is unblocked:
      - Add the `in progress` tag: `mcp__vibe_kanban__add_issue_tag` with `issue_id` and `tag_id: IN_PROGRESS_TAG_ID`.
      - Start a workspace: `mcp__vibe_kanban__start_workspace` with:
        - `name`: `"AFK Implement: <ISSUE_TITLE>"`
        - `executor`: `"CLAUDE_CODE"`
        - `issue_id`: the issue ID
        - `repositories`: `[{"repo_id": WORKTREE_REPO_ID, "branch": "main"}]`
        - `prompt`: `/kanban-afk-implement`

## Reporting

After both phases, output a brief summary:
- How many AFK candidates were found (Implement issues without HITL/done/in progress/draft/open)
- How many were eligible (unblocked)
- How many workspaces were started
- How many PRs were checked
- How many issues moved `draft` → `open` this tick
- How many PRs were merged and marked `done`
- How many linked Jira issues were transitioned to "In Review"
