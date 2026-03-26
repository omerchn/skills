---
name: kanban-prd-to-issues
description: Break a PRD into independently-grabbable Vibe Kanban issues using tracer-bullet vertical slices. Use when user wants to convert a PRD to issues, create implementation tickets, or break down a PRD into work items.
allowed-tools: mcp__vibe_kanban__list_organizations, mcp__vibe_kanban__list_projects, mcp__vibe_kanban__get_issue, mcp__vibe_kanban__list_issues, mcp__vibe_kanban__create_issue, mcp__vibe_kanban__update_issue, mcp__vibe_kanban__create_issue_relationship, Read, Glob, Grep
---

# PRD to Issues

Break a PRD into independently-grabbable Vibe Kanban issues using vertical slices (tracer bullets).

## Process

### 1. Locate the PRD

Ask the user for the PRD — either a Vibe Kanban issue ID/title, or paste the PRD text directly.

If the user provides a Vibe Kanban issue ID, fetch it with `mcp__vibe_kanban__get_issue`.

### 2. Explore the codebase (optional)

If you have not already explored the codebase, do so to understand the current state of the code.

### 3. Draft vertical slices

Break the PRD into **tracer bullet** issues. Each issue is a thin vertical slice that cuts through ALL integration layers end-to-end, NOT a horizontal slice of one layer.

Slices may be 'HITL' or 'AFK'. HITL slices require human interaction, such as an architectural decision or a design review. AFK slices can be implemented and merged without human interaction. Prefer AFK over HITL where possible.

<vertical-slice-rules>
- Each slice delivers a narrow but COMPLETE path through every layer (schema, API, UI, tests)
- A completed slice is demoable or verifiable on its own
- Prefer many thin slices over few thick ones
</vertical-slice-rules>

### 4. Quiz the user

Present the proposed breakdown as a numbered list. For each slice, show:

- **Title**: short descriptive name
- **Type**: HITL / AFK
- **Blocked by**: which other slices (if any) must complete first
- **User stories covered**: which user stories from the PRD this addresses

Ask the user:

- Does the granularity feel right? (too coarse / too fine)
- Are the dependency relationships correct?
- Should any slices be merged or split further?
- Are the correct slices marked as HITL and AFK?

Iterate until the user approves the breakdown.

### 5. Create the Vibe Kanban issues

Resolve the Work project once:

1. **List organizations** using `mcp__vibe_kanban__list_organizations` to get the org ID.
2. **List projects** using `mcp__vibe_kanban__list_projects` with the org ID. Find the project named **"Work"** and note its ID.

For each approved slice, in dependency order (blockers first):

3. **Create the issue** using `mcp__vibe_kanban__create_issue`:
   - `title`: Short, label-style name for the slice (e.g., "Add user auth endpoint", "Wire CSV export UI")
   - `description`: Use the issue body template below. Replace the PRD reference with the Vibe Kanban issue ID/URL if available, or a short PRD title otherwise.
   - `project_id`: The Work project ID from step 2

4. **Move the issue to the Implement column** using `mcp__vibe_kanban__update_issue`:
   - `issue_id`: The issue ID returned from step 3
   - `status`: `"Implement"`

5. **Link blockers** using `mcp__vibe_kanban__create_issue_relationship` for any "blocked by" relationships identified in step 4.

Do NOT close or modify the parent PRD issue.

<issue-template>
## Parent PRD

<prd-issue-id-or-title>

## What to build

A concise description of this vertical slice. Describe the end-to-end behavior, not layer-by-layer implementation. Reference specific sections of the parent PRD rather than duplicating content.

## Acceptance criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Blocked by

- Blocked by <issue-id> (if any)

Or "None - can start immediately" if no blockers.

## User stories addressed

Reference by number from the parent PRD:

- User story 3
- User story 7

</issue-template>

Present a summary to the user listing all created issue titles and their Vibe Kanban IDs, grouped by dependency order.
