---
name: kanban-start-jira-issue
description: Use when asked to start work on a Jira issue, create a Kanban issue from Jira, or plan a Jira ticket implementation. Takes a Jira issue URL, fetches details, creates a Vibe Kanban issue, and starts a Plan workspace.
user_invocable: true
allowed-tools: mcp__claude_ai_Atlassian__getJiraIssue, mcp__claude_ai_Atlassian__getAccessibleAtlassianResources, mcp__vibe_kanban__create_issue, mcp__vibe_kanban__start_workspace, mcp__vibe_kanban__list_repos, mcp__vibe_kanban__list_projects, mcp__vibe_kanban__list_organizations
---

# Start Jira Issue in Vibe Kanban

Fetch Jira issue details, create a Vibe Kanban issue, and start a Plan workspace to plan the implementation.

## Steps

### 1. Parse the Jira URL and Fetch Issue Details

The user provides a Jira issue URL (e.g., `https://<domain>.atlassian.net/browse/PROJ-123`).

Extract the **issue key** from the URL — it's the last path segment (e.g., `PROJ-123`).

1. Call `mcp__claude_ai_Atlassian__getAccessibleAtlassianResources` to get the cloud ID.
2. Call `mcp__claude_ai_Atlassian__getJiraIssue` with the cloud ID and issue key.

Collect:
- **Issue key** (e.g., `PROJ-123`)
- **Title/summary**
- **Description** (full text)
- **Status**
- **Issue type** (e.g., Story, Task, Bug)
- **Acceptance criteria** if present
- **Priority**
- **Components/labels** if present

### 2. Create Vibe Kanban Issue

1. **List organizations** using `mcp__vibe_kanban__list_organizations` to get the org ID.
2. **List projects** using `mcp__vibe_kanban__list_projects` with the org ID.
3. **Create an issue** using `mcp__vibe_kanban__create_issue`:
   - `title`: A very short description derived from the Jira issue title — concise label-style, e.g., "Table drift monitoring", "User auth refactor", "Fix payment timeout". Strip prefixes like "As a user..." and boil it down to the core topic.
   - `description`: `"Jira <JIRA_ISSUE_URL>"` — the exact URL the user provided.
   - `project_id`: Use the project ID from step 2
   - `priority`: Map from the Jira priority (Highest/High → "urgent", Medium → "medium", Low/Lowest → "low"). Default to "medium".

### 3. Start Plan Workspace

1. **List repos** using `mcp__vibe_kanban__list_repos` to find available repos. Pick the most relevant repo based on the Jira issue context (components, labels, or title keywords). If unsure, use "core" as default.
2. **Start a workspace** using `mcp__vibe_kanban__start_workspace`:
   - `name`: `"Plan: <SHORT_TITLE>"` — use the same short title from the Kanban issue
   - `executor`: `"CLAUDE_CODE"`
   - `issue_id`: The issue ID from step 2
   - `variant`: `"PLAN"`
   - `repositories`: Use the matched repo ID with branch `"main"`
   - `prompt`: `"Plan the following task: <REWRITTEN_TASK_DESCRIPTION>"` — Rewrite the Jira issue description into a clear, well-structured task brief for the planning agent. Clean up Jira formatting artifacts, consolidate scattered details, and present the task as a coherent description with clear requirements. Include acceptance criteria if present. Do NOT include the full Jira template — just a clean, readable task description that a planner can act on.

Present a summary to the user:
- Kanban issue title and ID
- Workspace name and status
- Let them know the planning agent is working on the implementation plan
