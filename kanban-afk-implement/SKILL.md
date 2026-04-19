---
name: kanban-afk-implement
description: AFK implementation skill. Runs inside a workspace, fetches issue and parent context, implements the work, creates a PR, and updates the issue with PR URL and tags.
user_invocable: false
allowed-tools: mcp__vibe_kanban__list_sessions, mcp__vibe_kanban__get_issue, mcp__vibe_kanban__update_issue, mcp__vibe_kanban__add_issue_tag, mcp__vibe_kanban__remove_issue_tag, mcp__vibe_kanban__list_issue_tags, mcp__vibe_kanban__list_tags, Read, Edit, Write, Glob, Grep, Bash, Agent, Skill
---

# AFK Implement

Autonomous implementation skill for AFK-tagged issues. Fetches the issue context, implements the work, creates a PR, and updates the issue.

## Steps

### 1. Detect Workspace Context and Fetch Issue

1. Call `mcp__vibe_kanban__list_sessions` **without** `workspace_id` to get the current session data.
2. Extract the `issue_id` from the session.
3. Fetch the issue using `mcp__vibe_kanban__get_issue` with the `issue_id`.
4. Store the issue's `description` as the **task brief**.

### 2. Fetch Parent Issue for Context (if exists)

1. Check if the issue has a `parent_issue_id`.
2. If yes, fetch the parent issue using `mcp__vibe_kanban__get_issue`.
3. Store the parent's `description` as **additional context** — this is typically the PRD or broader feature description.

### 3. Extract Jira Key

Extract the Jira URL from the issue description (or parent description if not found in the issue). Look for the pattern `Jira: (https://\S+)`.

From the Jira URL, extract the issue key matching `[A-Z]+-\d+` (e.g., `CORE-1234`).

If no Jira key can be found in either the issue or parent description, use the issue title slugified as the branch name prefix instead.

### 4. Implement the Work

Using the task brief from step 1 and the parent context from step 2, implement the described changes.

- Read the issue description carefully — it contains the "What to build" section and acceptance criteria.
- If a parent PRD is available, reference it for broader architectural context and user stories.
- Explore the codebase as needed to understand existing patterns.
- Write clean, well-structured code following existing conventions.
- Run tests if applicable.

### 5. Create the PR

Once implementation is complete, invoke the `/kanban-create-pr` skill with the Jira key:

```
/kanban-create-pr <JIRA_KEY>
```

Capture the **PR URL** from the output.

### 6. Update Issue with PR URL

1. Fetch the current issue description using `mcp__vibe_kanban__get_issue`.
2. Update the issue description using `mcp__vibe_kanban__update_issue`:
   - Prepend `PR: <PR_URL>` as the first line, followed by the existing description.
   - The final description format should be:

     ```
     PR: https://github.com/Orchid-Security/core/pull/456
     Jira: https://orchid-security.atlassian.net/browse/CORE-1234

     <rest of existing description>
     ```

### 7. Update Tags

1. Call `mcp__vibe_kanban__list_tags` with project ID `c7185330-ce37-4902-bb66-60d6a69b01b5` to get tag IDs.
2. Add the **"PR"** tag using `mcp__vibe_kanban__add_issue_tag`:
   - `tag_id`: `b57daa22-1068-44ab-a41f-84793e247af6`
3. Remove the **"in progress"** tag:
   - Call `mcp__vibe_kanban__list_issue_tags` with the issue ID to find the issue-tag relation ID for the "in progress" tag.
   - Call `mcp__vibe_kanban__remove_issue_tag` with that `issue_tag_id`.

### 8. Start PR Review

Invoke the `/kanban-start-pr-review` skill with the PR URL captured in step 5:

```
/kanban-start-pr-review <PR_URL>
```

## Rules

- **This skill runs autonomously** — do not ask questions or wait for user input.
- **Always create the PR before updating tags** — the PR URL must be in the description before adding the "PR" tag.
- **Never push to `main` or `master`** — the `/kanban-create-pr` skill handles branch creation.
- **If implementation fails** (tests don't pass, can't understand the requirements, etc.), stop and leave the issue as-is with the "in progress" tag. Do NOT add the "PR" tag.
