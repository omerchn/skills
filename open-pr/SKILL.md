---
name: open-pr
description: Use when asked to open a PR, mark a PR as ready for review, or transition a draft PR to open. Runs inside a Vibe Kanban workspace context. Finds the PR URL from the workspace issue, updates the PR description with a test plan, marks it ready for review, and spawns Code Review and Code Simplifier workspaces.
user_invocable: true
allowed-tools: Bash(gh *), Bash(git *), mcp__vibe_kanban__list_sessions, mcp__vibe_kanban__get_issue, mcp__vibe_kanban__list_organizations, mcp__vibe_kanban__list_projects, mcp__vibe_kanban__list_repos, mcp__vibe_kanban__start_workspace, mcp__vibe_kanban__update_issue, Read, Glob, Grep, AskUserQuestion
---

# Open PR

Mark a draft PR as ready for review, fill in the test plan, and spawn review + simplifier workspaces under the current Vibe Kanban issue.

## Steps

### 1. Find the PR URL

Try these sources in order until a PR URL is found:

**a) From the Vibe Kanban workspace issue:**

1. Call `mcp__vibe_kanban__list_sessions` (without `workspace_id`) to get the current session data.
2. Extract the `issue_id` from the session.
3. Fetch the issue using `mcp__vibe_kanban__get_issue`.
4. Look for a PR URL in the issue description — match the pattern `https://github.com/[^/]+/[^/]+/pull/\d+`.

**b) From conversation context:**

If no PR URL was found in the issue, check whether a PR URL was mentioned earlier in the conversation or passed as an argument (e.g., `/open-pr https://github.com/Orchid-Security/core/pull/1234`).

**c) Ask the user:**

If still not found, use `AskUserQuestion` to ask the user for the PR URL. Do not proceed without it.

Store the PR URL and extract the PR number from it.

### 2. Determine the GitHub Repo

- If the PR URL contains the full `OWNER/REPO` path, extract it.
- Otherwise, detect the current repo:
  ```bash
  gh repo view --json nameWithOwner -q .nameWithOwner
  ```

### 3. Read the Current PR

Fetch the PR details to understand the changes:

```bash
gh pr view <PR_NUMBER> --repo <GITHUB_REPO> --json title,body,headRefName,baseRefName,files,commits
```

### 4. Fill in the Test Plan

Analyze the PR's changed files and commits to write a meaningful test plan. Replace the placeholder `- [ ] TBD` in the PR body (or the empty test plan section) with concrete test items.

The test plan should include:
- Specific scenarios to verify based on the actual code changes
- Edge cases worth testing
- Any integration or regression concerns
- Keep it concise — 3-8 bullet items, each a checkbox (`- [ ]`)

Update the PR description:

```bash
gh pr edit <PR_NUMBER> --repo <GITHUB_REPO> --body "$(cat <<'EOF'
<UPDATED_PR_BODY_WITH_TEST_PLAN>
EOF
)"
```

Preserve the existing Summary and Jira Ticket sections — only replace the Test Plan content.

### 5. Mark PR as Ready for Review

```bash
gh pr ready <PR_NUMBER> --repo <GITHUB_REPO>
```

### 6. Resolve Vibe Kanban Repo and Org

1. **List organizations** using `mcp__vibe_kanban__list_organizations` to get the org ID.
2. **List projects** using `mcp__vibe_kanban__list_projects` with the org ID.
3. **List repos** using `mcp__vibe_kanban__list_repos` to find the matching repo ID.
   - Match the GitHub `OWNER/REPO` against available Vibe Kanban repos (case-insensitive).

### 7. Spawn Two Workspaces

Start **both workspaces** under the current issue (from step 1), using `origin/main` as the base branch.

**Workspace 1 — Code Review:**

Use `mcp__vibe_kanban__start_workspace`:
- `name`: `"Code Review"`
- `executor`: `"CLAUDE_CODE"`
- `issue_id`: The current Vibe Kanban issue ID
- `repositories`: Use the matched repo ID with branch `"main"`
- `prompt`: `/review <PR_URL>`

**Workspace 2 — Code Simplifier:**

Use `mcp__vibe_kanban__start_workspace`:
- `name`: `"Code Simplifier"`
- `executor`: `"CLAUDE_CODE"`
- `issue_id`: The current Vibe Kanban issue ID
- `repositories`: Use the matched repo ID with branch `"main"`
- `prompt`: `start code-simplifier agent on PR <PR_URL> in current workspace`

### 8. Report to User

Present a summary:
- PR URL and new status (ready for review)
- Test plan items added
- Both workspace names and their status
- Let the user know the review and simplifier are running

## Rules

- **PR URL resolution order**: workspace issue → conversation context → ask user. Never guess a PR URL.
- **Preserve existing PR description content** — only update the Test Plan section.
- **Both workspaces must use `origin/main` as the base branch.**
- **Never skip the test plan** — always analyze the changes and write meaningful test items.
