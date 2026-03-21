---
name: kanban-start-pr-review
description: Use when asked to review a PR, start a PR review, or kick off a code review for a pull request. Fetches PR details, resolves Jira ticket from branch name, creates a Vibe Kanban issue and workspace to run the review in.
user_invocable: true
allowed-tools: Bash(gh *), Bash(git *), mcp__claude_ai_Atlassian__getJiraIssue, mcp__claude_ai_Atlassian__searchJiraIssuesUsingJql, mcp__claude_ai_Atlassian__getAccessibleAtlassianResources, mcp__vibe_kanban__create_issue, mcp__vibe_kanban__start_workspace, mcp__vibe_kanban__list_repos, mcp__vibe_kanban__list_projects, mcp__vibe_kanban__list_organizations, Read, Glob, Grep
---

# Assisted PR Review

Gather PR context, resolve the Jira ticket, create a Vibe Kanban issue, and start a workspace that will perform the full review.

## Steps

### 1. Get PR Details

The user provides a PR number or URL. Extract the PR number and determine the GitHub repo (`OWNER/REPO`).

- If the user provides a **full GitHub URL**, extract `OWNER/REPO` from it.
- If the user provides **just a PR number**, detect the current repo:
  ```bash
  gh repo view --json nameWithOwner -q .nameWithOwner
  ```

Fetch PR details:
```bash
gh pr view <PR_NUMBER> --repo <GITHUB_REPO> --json title,author,headRefName,baseRefName,body,files
```

Extract the **title**, **author login**, **head branch**, **base branch**, **body/description**, and **list of changed files** (with additions/deletions per file).

### 2. Add Yourself as Reviewer & React to PR

React with the eyes emoji on the PR description to signal you're looking at it.

First, resolve your GitHub username:
```bash
gh api user -q .login
```

Second, add the eyes reaction.
```bash
gh api repos/<OWNER>/<REPO>/issues/<PR_NUMBER>/reactions -f content=eyes
```

### 3. Resolve Jira Ticket from Branch Name

Extract the Jira ticket key from the branch name prefix. The pattern is typically `<PROJECT>-<NUMBER>` at the start of the branch name (e.g., `CORE-1234-add-feature` → ticket is `CORE-1234`).

Use the regex pattern: first match of `[A-Z]+-\d+` in the branch name.

If a ticket key is found, fetch the Jira issue using `mcp__claude_ai_Atlassian__getJiraIssue` (you may need to call `mcp__claude_ai_Atlassian__getAccessibleAtlassianResources` first to get the cloud ID).

Collect the **Jira Ticket Summary**:
- Ticket key and title
- Status
- Description (first 500 chars)
- Acceptance criteria if present

If no ticket key can be extracted from the branch name, note this and move on.

### 4. Create Vibe Kanban Issue & Start Workspace

Create a Vibe Kanban issue to track this PR review, then start a workspace that will perform the entire review.

1. **List organizations** using `mcp__vibe_kanban__list_organizations` to get the org ID.
2. **List projects** using `mcp__vibe_kanban__list_projects` with the org ID.
3. **Create an issue** using `mcp__vibe_kanban__create_issue`:
   - `title`: `"PR Review: <PR_TITLE> (#<PR_NUMBER>)"`
   - `description`: Include the PR URL, author, branch, and Jira ticket key (if found). Example:
     ```
     Review PR #<NUMBER> by <AUTHOR>
     Branch: <HEAD_BRANCH> → <BASE_BRANCH>
     Repo: <OWNER/REPO>
     Jira: <TICKET_KEY or "N/A">
     ```
   - `project_id`: Use the project ID from step 2
   - `priority`: `"medium"`
4. **List repos** using `mcp__vibe_kanban__list_repos` to find the matching repo ID. Match the repo name from the GitHub `OWNER/REPO` against the available Vibe Kanban repos (case-insensitive). If no match is found, pick the closest match or use "core" as default.
5. **Start the review workspace** using `mcp__vibe_kanban__start_workspace`:
   - `name`: `"PR Review #<PR_NUMBER>"`
   - `executor`: `"CLAUDE_CODE"`
   - `issue_id`: The issue ID from step 3
   - `repositories`: Use the matched repo ID with branch - the PRs branch from remote origin. If it's `core` repo - then use the `core-worktrees` repo.
   - `prompt`: Build the prompt using the template below. Replace all `<PLACEHOLDERS>` with actual values. If the Jira ticket was successfully fetched, fill in the Jira section; otherwise use `"N/A"` for those fields.

--- BEGIN REVIEW PROMPT ---

/review <PR_URL>

## Jira Ticket Context

- **Ticket:** <JIRA_TICKET_KEY or "N/A">
- **Title:** <JIRA_TICKET_TITLE or "N/A">
- **Status:** <JIRA_STATUS or "N/A">
- **Description:** <JIRA_DESCRIPTION_FIRST_500_CHARS or "N/A">
- **Acceptance Criteria:** <JIRA_ACCEPTANCE_CRITERIA or "N/A">

--- END REVIEW PROMPT ---

The `/review` command must always be the **first line** of the prompt. ALWAYS use `/review`, NEVER `/code-review`.

6. **Start a second annotation workspace** using `mcp__vibe_kanban__start_workspace`:
   - `name`: `"PR Annotation #<PR_NUMBER>"`
   - `executor`: `"CLAUDE_CODE"`
   - `issue_id`: The issue ID from step 3
   - `repositories`: Same repo ID as above, same PR branch from remote origin (same `core-worktrees` rule applies).
   - `prompt`: The exact text below, with `<PR_NUMBER>` and `<OWNER/REPO>` replaced:

--- BEGIN ANNOTATION PROMPT ---

You are annotating the changes in PR #<PR_NUMBER> (<OWNER/REPO>) so a human reviewer can understand each change at a glance — without needing to compare before/after files.

## Step 1: Collapse branch commits into staged changes

```bash
git fetch origin
git reset --mixed origin/main
```

This squashes all commits on the branch into a single set of unstaged changes, giving you a clean diff of everything that was added or modified.

## Step 2: Collect changed files

Run:
```bash
git diff --name-only origin/main
```

Filter out test files — skip anything matching `*.spec.*`, `*.test.*`, `*.e2e-spec.*`, or under a `__tests__/` or `test/` directory.

## Step 3: Spawn a sub-agent per logical block

For each non-test file, read its full diff:
```bash
git diff origin/main -- <file>
```

Identify the **logical blocks of changes** in that diff — a new function, a modified conditional, a new variable or constant, a class/method change, a new import group, etc.

For **each logical block**, spawn a sub-agent with this prompt:

> You are inserting a code annotation comment into `<FILE_PATH>`.
>
> Here is the diff of the logical block you are annotating:
> ```
> <BLOCK_DIFF>
> ```
>
> Here is the full current file content for context:
> ```
> <FILE_CONTENT>
> ```
>
> Task: Immediately above the changed code in the file, insert a comment using the file's native comment syntax. The comment should explain in 1–4 lines:
> - **What** this block does (plain language)
> - **Why** it was added or changed (infer from the diff shape and surrounding code)
>
> Edit the file directly. Do not summarize or explain — just insert the comment and save the file.

Run all sub-agents for a given file **sequentially** (one block at a time) to avoid concurrent write conflicts on the same file. Sub-agents across **different files** can run in parallel.

## Step 4: Verify

After all sub-agents complete, run:
```bash
git diff origin/main
```

Confirm every meaningful change has an annotation above it. If any logical block is missing a comment, add one inline.

Do not commit. Leave the annotations as local changes so the author can review and amend before pushing.

--- END ANNOTATION PROMPT ---

Present a summary to the user:
- Kanban issue title and ID
- Both workspace names and statuses
- Let them know the review is running in the first workspace and the annotation is running in the second
