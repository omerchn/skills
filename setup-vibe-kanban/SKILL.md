---
name: setup-vibe-kanban
description: Use only when the user runs `/setup-vibe-kanban`. Bootstraps a new or incomplete Vibe Kanban to mirror the reference setup (projects, tags, repos, repo scripts) via a stepwise manual checklist plus automated verification.
user_invocable: true
allowed-tools: mcp__vibe_kanban__list_organizations, mcp__vibe_kanban__list_projects, mcp__vibe_kanban__list_tags, mcp__vibe_kanban__list_repos, mcp__vibe_kanban__update_setup_script
---

# Setup Vibe Kanban

Mirror the reference Vibe Kanban setup onto the user's currently-connected kanban. The MCP exposes no `create_project`, `create_tag`, or `create_repo` tools, so structural creation is manual: the skill prints a checklist, the user creates items in the UI, says "done", and the skill verifies via `list_*` calls. Repo setup scripts are written automatically afterwards.

The skill is idempotent: extras are tolerated, only missing items are flagged.

## Reference Setup (hardcoded)

### Projects

- `Work`
- `Reviews`

### Tags

In project **Work** (14 tags):

```
bug
feature
documentation
enhancement
done
In Review
Testing In Dev
Ready For Staging
Grilled
AFK
HITL
blocked
PR
in progress
```

In project **Reviews** (6 tags):

```
bug
feature
documentation
enhancement
mine
done
```

### Repos

6 repos (names only — the user points each at their own local clone in the UI):

```
core
core-2
core-worktrees
helm
integrations
snowflake
```

### Repo setup scripts

After repos exist, set `setup_script = "pnpm install"` on:

- `core`
- `core-worktrees`

All other repos: no scripts.

## Steps

### 1. Diff phase — what's already there?

Call these in parallel:

- `mcp__vibe_kanban__list_organizations`
- `mcp__vibe_kanban__list_repos`
- `mcp__vibe_kanban__list_projects` — needs `organization_id`. Pick the org with `is_personal: true`. If there are zero personal orgs, abort and tell the user (the personal org is auto-created per account; absence means the MCP isn't connected to a real account).

Once projects are returned, capture the IDs of `Work` and `Reviews` (if they exist), then call `mcp__vibe_kanban__list_tags` for each existing project in parallel.

Compute the deltas (expected − actual) for: projects, Work tags, Reviews tags, repos. Print a compact diff like:

```
Projects:    ✓ Work    ✗ Reviews
Work tags:   12/14 present, missing: PR, in progress
Reviews:     project missing — tags will be checked after creation
Repos:       4/6 present, missing: helm, snowflake
Scripts:     core ✓ pnpm install, core-worktrees ✗ (currently null)
```

If everything matches (all deltas empty AND both target scripts already correct), print "Setup already matches reference. Nothing to do." and exit.

Otherwise, proceed stepwise. Skip any step whose delta is already empty.

### 2. Step — Projects

If `Work` and/or `Reviews` are missing, print:

```
Create these projects in the Vibe Kanban UI, then say "done":
  - Work
  - Reviews   (only list the missing ones)
```

Wait for the user. After "done", call `list_projects` again. If the delta is still non-empty, print "Still missing: [...]" and wait for "done" again. Loop until both projects exist.

### 3. Step — Tags

Capture the (now-existing) `Work` and `Reviews` project IDs from the latest `list_projects` result.

Call `list_tags` for each in parallel. For each project with a non-empty missing-tags delta, print:

```
In project "<Work | Reviews>", create these tags (names only — colors don't matter), then say "done":
  - <missing tag 1>
  - <missing tag 2>
  ...
```

If both projects need tags, print one combined message with two sub-lists. After "done", re-list and loop until both deltas are empty.

### 4. Step — Repos

If any repos from the reference list are missing, print:

```
Create these repos in the Vibe Kanban UI (point each at your local clone), then say "done":
  - <missing repo 1>
  - <missing repo 2>
  ...
```

After "done", call `list_repos`. Loop until all 6 reference repos are present by name.

### 5. Step — Repo setup scripts (automated)

Once all 6 repos exist, look up the IDs of `core` and `core-worktrees` from the latest `list_repos` result. For each, if its `setup_script` is not already `"pnpm install"`, call `mcp__vibe_kanban__update_setup_script` with the matching `repo_id` and `script: "pnpm install"`. Run both updates in parallel.

(`get_repo` is not in `allowed-tools` because `list_repos` only returns id+name. Trust the diff phase's report — if a script was already correct there, skip the update; otherwise just run it. Re-running with the same value is harmless.)

For simplicity: always run both updates unless the diff phase confirmed both scripts are already correct. The cost is two no-op MCP calls in the worst case.

### 6. Final report

Print a one-line confirmation summarizing what was created/updated, e.g.:

```
Setup complete.
  Projects: Reviews created (Work already existed).
  Tags: 2 added in Work, 6 added in Reviews.
  Repos: helm, snowflake created.
  Scripts: core-worktrees → pnpm install.
```

If nothing was changed (all skipped because already complete), report that instead.

## Notes

- **Names only.** Tag colors are not part of the reference (no `create_tag` MCP tool means colors must be set manually in the UI; the user opted out of color matching). The new kanban will look visually different from the original — that's expected.
- **Repo paths are user-provided.** The MCP doesn't expose a repo's local path or remote URL, and there's no `create_repo` tool, so the user picks where each repo points to in the UI.
- **Issues, sessions, workspaces are out of scope.** This skill only sets up structural state.
- **Org is not created.** Personal orgs are auto-created per user account; the skill picks the existing personal org and aborts if there isn't one.
