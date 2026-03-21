---
name: create-pr
description: Use when asked to create a PR, push and open a pull request, or start a draft PR. Pushes to a remote branch with Jira key prefix, keeps local branch unchanged, and creates a draft PR.
user_invocable: true
allowed-tools: Bash(git *), Bash(gh *), Read, Glob, Grep, AskUserQuestion, mcp__vibe_kanban__list_sessions, mcp__vibe_kanban__get_issue, mcp__vibe_kanban__update_issue
---

# Create PR

Push changes to a remote branch named `<JIRA_KEY>-<slugified-title>` (keeping the local branch as-is) and create a draft PR.

## Inputs

The user may provide:
- **Jira ticket key** (e.g., `CORE-1234`) — as an argument or from context.
- If not provided, **ask the user** using `AskUserQuestion`.

## Steps

### 1. Get the Jira Key

- Check if the user provided a Jira key as an argument (e.g., `/create-pr CORE-1234`).
- If the current branch name starts with a pattern matching `[A-Z]+-\d+`, extract it as the Jira key.
- If still not found, **ask the user** for the Jira key. Do not proceed without it.

### 2. Safety Checks

- Run `git branch --show-current` to get the current branch.
- If on `main` or `master`, **stop** and tell the user to switch to a feature branch first.

### 3. Stage and Commit Changes

1. Run `git status` and `git diff` to understand changes.
2. If there are uncommitted changes:
   - Stage all changes: `git add -A`
   - Create a conventional commit:
     - Infer type: `feat`, `fix`, `refactor`, `chore`, `test`
     - Concise, lowercase, imperative description
     - **No co-author line**
     - **Always use `--no-verify`**
     ```bash
     git commit --no-verify -m "type(scope): description"
     ```
3. If the working tree is clean, skip to step 5.

### 4. Determine Remote Branch Name

Generate the remote branch name: `<JIRA_KEY>-<slugified-description>` where:
- `<JIRA_KEY>` is the Jira ticket key (e.g., `CORE-1234`)
- `<slugified-description>` is derived from the PR title or commit subject — lowercase, hyphens, no special chars, max 60 chars total

Example: `CORE-1234-add-identity-flow-filtering`

**Important:** The local branch name stays unchanged. Only the remote tracking branch uses this format.

### 5. Push to Remote

Push the local branch to the remote under the new name:

```bash
git push -u origin HEAD:<REMOTE_BRANCH_NAME>
```

This keeps the local branch name as-is while the remote branch gets the Jira-prefixed name.

### 6. Create a Draft PR

Use conventional commit format for the PR title: `type(scope): description`

```bash
gh pr create --draft --head "<REMOTE_BRANCH_NAME>" --title "type(scope): description" --body "$(cat <<'EOF'
## Summary

<Brief description of what this PR does>

## Jira Ticket

[<JIRA_KEY>](https://orchid-security.atlassian.net/browse/<JIRA_KEY>)

## Test Plan

- [ ] TBD
EOF
)"
```

Capture the **PR URL** from the output.

### 7. Update Vibe Kanban Issue (if in workspace context)

Try to detect if you're inside a Vibe Kanban workspace:

1. Call `mcp__vibe_kanban__list_sessions` **without** a `workspace_id`. If this succeeds and returns session data, you're inside a workspace.
2. From the session data, extract the `issue_id` linked to the workspace.
3. Fetch the issue using `mcp__vibe_kanban__get_issue` to get the current description.
4. Update the issue description using `mcp__vibe_kanban__update_issue`:
   - `issue_id`: The issue ID from the workspace
   - `description`: Append `PR <PR_URL>` to the existing description (preserve existing content)

If the `list_sessions` call fails or returns no data, skip this step silently — the user is not in a workspace context.

### 8. Report to User

Present a summary:
- Local branch name (unchanged)
- Remote branch name
- Commit hash
- Draft PR URL

## Rules

- **Never push to `main` or `master`** — refuse if on main with no way to create a branch.
- **Always use `--no-verify`** — skip hooks on commits and pushes.
- **Never ask to confirm the commit message** — just do it.
- **No co-author line** in commits.
- **Always create a draft PR** — never a ready-for-review PR.
- **Local branch name must not be changed** — only the remote branch gets the Jira-prefixed name.
- **Always ask for the Jira key if not provided** — never guess or skip it.
