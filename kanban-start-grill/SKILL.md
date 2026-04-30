---
name: kanban-start-grill
description: Use when asked to start a grill session from a Jira issue. Takes a Jira URL, creates a Grill issue in Vibe Kanban, and starts a workspace with /grill-me.
user_invocable: true
allowed-tools: mcp__claude_ai_Atlassian__getJiraIssue, mcp__claude_ai_Atlassian__getAccessibleAtlassianResources, mcp__vibe_kanban__create_issue, mcp__vibe_kanban__update_issue, mcp__vibe_kanban__start_workspace, mcp__vibe_kanban__list_repos, mcp__vibe_kanban__list_projects, mcp__vibe_kanban__list_organizations
---

# Start Grill Session from Jira Issue

Fetch Jira issue details, create a Vibe Kanban issue in the Grill column, and start a workspace running `/grill-me`.

## Inputs

The user provides a **Jira issue URL** (e.g., `https://orchid-security.atlassian.net/browse/CORE-1234`).

## Steps

### 1. Parse the Jira URL and Fetch Issue Details

Extract the **issue key** from the URL — it's the last path segment (e.g., `CORE-1234`).

1. Call `mcp__claude_ai_Atlassian__getAccessibleAtlassianResources` to get the cloud ID.
2. Call `mcp__claude_ai_Atlassian__getJiraIssue` with the cloud ID and issue key.

Collect:
- **Issue key** (e.g., `CORE-1234`)
- **Title/summary**

### 2. Create Vibe Kanban Issue

Resolve the **Work** project:
1. Call `mcp__vibe_kanban__list_organizations` → org ID
2. Call `mcp__vibe_kanban__list_projects` with the org ID → find the project named `"Work"` (case-insensitive) and note its ID.

Create an issue using `mcp__vibe_kanban__create_issue`:
- `title`: A short label-style title derived from the Jira issue summary. Strip prefixes like "As a user..." and boil it down to the core topic (e.g., "Table drift monitoring", "Fix payment timeout").
- `description`: `Jira: <JIRA_ISSUE_URL>` — the exact URL the user provided.
- `project_id`: The Work project ID from above.

Move the issue to the **Grill** column using `mcp__vibe_kanban__update_issue`:
- `issue_id`: The issue ID returned above
- `status`: `"Grill"`

### 3. Start Grill Workspace

Resolve the worktree repo:
1. Call `mcp__vibe_kanban__list_repos` and find the repo named `"core-worktrees"` (case-insensitive). If none matches, fall back to `"core"`.

Start a workspace using `mcp__vibe_kanban__start_workspace`:
- `name`: `"Grill: <SHORT_TITLE>"` — use the same short title from the Kanban issue
- `executor`: `"CLAUDE_CODE"`
- `issue_id`: The issue ID from step 2
- `repositories`: Use the matched repo ID with branch `"main"`
- `prompt`: `/grill-me <JIRA_ISSUE_URL>`

### 4. Report to User

Present a summary:
- Kanban issue title and ID
- Workspace name and status
- Let them know the grill workspace is ready for them to join
