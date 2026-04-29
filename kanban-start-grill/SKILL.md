---
name: kanban-start-grill
description: Use when asked to start a grill session from a Jira issue. Takes a Jira URL, creates a Grill issue in Vibe Kanban, and starts a workspace with /grill-me.
user_invocable: true
allowed-tools: mcp__claude_ai_Atlassian__getJiraIssue, mcp__claude_ai_Atlassian__getAccessibleAtlassianResources, mcp__vibe_kanban__create_issue, mcp__vibe_kanban__update_issue, mcp__vibe_kanban__start_workspace, mcp__vibe_kanban__list_repos
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

Create an issue using `mcp__vibe_kanban__create_issue`:
- `title`: A short label-style title derived from the Jira issue summary. Strip prefixes like "As a user..." and boil it down to the core topic (e.g., "Table drift monitoring", "Fix payment timeout").
- `description`: `Jira: <JIRA_ISSUE_URL>` — the exact URL the user provided.
- `project_id`: `c7185330-ce37-4902-bb66-60d6a69b01b5`

Move the issue to the **Grill** column using `mcp__vibe_kanban__update_issue`:
- `issue_id`: The issue ID returned above
- `status`: `"Grill"`

### 3. Start Grill Workspace

Start a workspace using `mcp__vibe_kanban__start_workspace`:
- `name`: `"Grill: <SHORT_TITLE>"` — use the same short title from the Kanban issue
- `executor`: `"CLAUDE_CODE"`
- `issue_id`: The issue ID from step 2
- `repositories`: Use repo ID `f1819923-d554-4f4b-a344-6607d6912c59` (core-worktrees) with branch `"main"`
- `prompt`: `/grill-me <JIRA_ISSUE_URL>`

### 4. Report to User

Present a summary:
- Kanban issue title and ID
- Workspace name and status
- Let them know the grill workspace is ready for them to join
