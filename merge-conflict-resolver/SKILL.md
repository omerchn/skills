---
name: merge-conflict-resolver
description: Resolve git merge conflicts by analyzing both sides, presenting clear diffs, and applying correct resolutions. Use when the user runs git merge and encounters conflicts, asks to merge a branch, or mentions merge conflicts.
---

# Merge Conflict Resolver

Systematic workflow for resolving git merge conflicts during `git merge`.

## Phase 1: Pre-Merge Check

Before merging, verify the workspace is ready:

```bash
git branch --show-current
git status --short
```

**Abort if**:
- There are uncommitted changes — ask the user to commit or stash first
- The working tree is dirty — don't risk mixing unrelated changes with conflict resolution

## Phase 2: Execute Merge

Run the merge and capture output. Default to `main` if the user didn't specify a target branch:

```bash
git merge main
```

If the user specified a different branch, use that instead:

```bash
git merge <target-branch>
```

If the merge succeeds cleanly (exit code 0), report success and stop.

If conflicts occur, proceed to Phase 3.

## Phase 3: Identify Conflicts

Parse the merge output to list conflicted files. Verify with:

```bash
git diff --name-only --diff-filter=U
```

Present a summary to the user:

| # | File | Status |
|---|------|--------|
| 1 | path/to/file.ts | CONFLICT |
| 2 | path/to/other.ts | CONFLICT |

## Phase 4: Resolve Each File

For each conflicted file:

### 4a. Read the full file

Read the entire file to see all conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) in context.

### 4b. Analyze each conflict block

For every conflict block, determine:

1. **What HEAD (current branch) added or changed** — and why
2. **What the incoming branch added or changed** — and why
3. **Whether the changes overlap or are independent**

Classification:

| Type | Description | Resolution |
|------|-------------|------------|
| **Additive** | Both sides added independent code at the same location | Keep both additions |
| **Rename/Move** | One side renamed or moved something the other side also touched | Use the renamed version, keep the other side's additions |
| **True conflict** | Both sides modified the same lines with different intent | Requires judgment — present both options to the user |
| **Divergent refactor** | One side refactored code the other side modified | Understand the refactor, adapt the other side's changes to fit |

### 4c. Apply resolution

- For **additive** and **rename/move** conflicts: resolve automatically by keeping both sides' contributions
- For **true conflicts** and **divergent refactors**: present both versions to the user with an explanation and a recommended resolution, then ask for confirmation before applying

### 4d. Verify no markers remain

After resolving, confirm no conflict markers remain in the file:

```bash
grep -rn '<<<<<<\|======\|>>>>>>' <file>
```

### 4e. Check related exports

If the conflict involved new exports (schemas, types, functions), verify they are re-exported from the relevant barrel file (`index.ts`).

## Phase 5: Stage and Verify

Stage resolved files:

```bash
git add <resolved-files>
```

Run a final check for leftover conflict markers across all files:

```bash
git diff --check
```

## Phase 6: Confirm Before Committing

**Always ask the user for confirmation before committing.** Present:

1. A summary of each conflict and how it was resolved
2. The `git status` output showing staged files

Only after user approval:

```bash
git commit --no-edit
```

If the commit fails (e.g., pre-commit hooks), report the failure and help fix it.

## Resolution Principles

- **Read before editing** — always read the full conflicted file before making changes
- **Preserve both sides** — when changes are independent, keep all additions from both branches
- **Follow the rename** — if one branch renamed/moved something, use the new name and adapt the other side
- **Check usage sites** — when an import conflicts, check how the imported symbol is actually used in the file to determine which version is correct
- **Barrel exports matter** — new schemas, types, or functions must be re-exported from `index.ts` to be importable
- **No guessing on true conflicts** — when both sides intentionally changed the same logic differently, present both options and let the user decide

## Anti-patterns

- **Don't blindly accept one side** — "accept theirs" or "accept ours" loses changes
- **Don't commit without user confirmation** — always present the resolution summary first
- **Don't resolve partial conflicts** — resolve ALL conflict blocks in a file before moving to the next
- **Don't skip the conflict marker check** — leftover markers break compilation
- **Don't ignore auto-merged files** — files that merged cleanly may still have semantic issues (e.g., duplicate imports, conflicting logic); scan them if the merge touched related code
