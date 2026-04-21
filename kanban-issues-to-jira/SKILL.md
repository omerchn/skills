---
name: kanban-issues-to-jira
description: Push every Vibe Kanban slice issue created from a PRD into Jira as a sub-task of the parent Jira ticket. High-level titles and descriptions only — no technical details. Run by a human AFTER /kanban-prd-to-issues has finished, from the same PRD workspace.
user_invocable: true
allowed-tools: mcp__vibe_kanban__list_sessions, mcp__vibe_kanban__get_issue, mcp__vibe_kanban__list_issues, mcp__vibe_kanban__list_organizations, mcp__vibe_kanban__list_projects, mcp__claude_ai_Atlassian__getAccessibleAtlassianResources, mcp__claude_ai_Atlassian__getJiraIssue, mcp__claude_ai_Atlassian__createJiraIssue, mcp__claude_ai_Atlassian__getJiraProjectIssueTypesMetadata, mcp__atlassian__getAccessibleAtlassianResources, mcp__atlassian__getJiraIssue, mcp__atlassian__createJiraIssue, mcp__atlassian__getJiraProjectIssueTypesMetadata
---

# Kanban Issues to Jira

Create a Jira sub-task under the parent Jira ticket for every Vibe Kanban slice issue produced by `/kanban-prd-to-issues`.

**When to run:** After `/kanban-prd-to-issues` completes, from the same workspace (linked to the PRD issue). The human triggers this manually.

**Assumptions carried over from `/kanban-prd-to-issues`:**
- The PRD Kanban issue description contains a `Jira: <URL>` line pointing to the parent Jira ticket.
- Each child slice Kanban issue's description contains `## Parent PRD` followed by the PRD's Kanban issue ID.

Use whichever Atlassian MCP prefix is available in the session (`mcp__atlassian__*` or `mcp__claude_ai_Atlassian__*`). The tool names below are identical across both prefixes.

## Process

### 1. Resolve the PRD issue from the current session

1. Call `mcp__vibe_kanban__list_sessions` **without** `workspace_id` to get the current session.
2. Extract the `issue_id` from the session.
3. Fetch the issue with `mcp__vibe_kanban__get_issue`.
4. **If the issue's `status` is NOT `"PRD"`, stop and tell the user:**

   > This skill must be run from a workspace linked to a **PRD** issue. The current issue is in the **"<status>"** column. Please run it from the PRD workspace used for `/kanban-prd-to-issues`.

5. Store the PRD issue's `id`, `title`, and `description`.
6. Extract the Jira URL from the PRD description — look for `Jira: (https://\S+)`. If none is found, stop and tell the user the parent PRD has no Jira URL to attach sub-tasks to.
7. Parse the parent Jira **issue key** (last path segment of the URL, e.g., `PROJ-123`) and **project key** (prefix before the dash, e.g., `PROJ`).

### 2. Find the child slice issues

1. Resolve the **Work** project once:
   - `mcp__vibe_kanban__list_organizations` → org ID
   - `mcp__vibe_kanban__list_projects` with the org ID → find the project named `"Work"` and note its ID
2. Call `mcp__vibe_kanban__list_issues` scoped to the Work project.
3. Filter to issues whose description contains the PRD issue ID beneath `## Parent PRD`. These are the slice issues created by `/kanban-prd-to-issues`.
4. Preserve the `create_issue_relationship` "blocked by" order so sub-tasks appear in a sensible order in Jira — topologically sort so blockers come first.

### 3. Confirm the list with the user

Present a numbered list to the user showing each child issue's title and Kanban ID. Ask:

- Is this the correct set to push to Jira?
- Any to skip or reorder?

Do not proceed until the user confirms.

### 4. Resolve Jira context

1. Call `getAccessibleAtlassianResources` → cloud ID.
2. Call `getJiraIssue` with the cloud ID and the parent issue key to verify it exists.
3. Call `getJiraProjectIssueTypesMetadata` with the project key and find the sub-task issue type. Prefer the entry with `subtask: true`; otherwise fall back to one whose name is `"Sub-task"` (or `"Subtask"`). Note its exact name.

### 5. Create a Jira sub-task for each confirmed child issue

For each child Kanban issue, in the confirmed order:

1. **High-level title.** Start from the Kanban issue title. Rewrite as user-facing if it leaks implementation terms (e.g., "Wire up `/auth` endpoint" → "User sign-in"). Keep it short.
2. **High-level description.** Distill from the child issue's `## What to build` section and its `## User stories addressed`. Rewrite as user-facing behavior.

   <description-rules>
   - **No file paths, function names, schema fields, endpoint shapes, library names, or step-by-step implementation.**
   - No references to "the parent PRD" or Kanban IDs.
   - Describe the user-visible outcome and, where relevant, the user stories it serves.
   - Keep it short: a couple of sentences plus an optional bulleted list of outcomes.
   </description-rules>

3. Call `createJiraIssue` with:
   - `cloudId`: from step 4.1
   - `projectKey`: parent project key from step 1.7
   - `issueTypeName`: the sub-task type from step 4.3
   - `summary`: the high-level title
   - `description`: the high-level description
   - Parent linkage: set the parent issue key (parameter name depends on the tool — commonly `parentKey`, `parent`, or an additional field on `additionalFields`). If the tool rejects the parameter, re-call with the alternate name; Jira requires the parent be set at creation for sub-task types.

4. Capture the returned Jira issue key and URL.

If a sub-task creation fails, report the failure to the user but continue with the remaining issues rather than aborting the batch.

### 6. Summarize

Present a table to the user:

| Kanban issue | Jira sub-task key | Jira URL |
|---|---|---|

Followed by:
- The parent Jira ticket URL.
- Any failures, clearly flagged.
