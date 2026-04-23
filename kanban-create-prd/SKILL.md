---
name: kanban-create-prd
description: Create a PRD through user interview, codebase exploration, and module design, then submit as a Vibe Kanban issue. Use when user wants to write a PRD, create a product requirements document, or plan a new feature.
allowed-tools: mcp__vibe_kanban__list_organizations, mcp__vibe_kanban__list_projects, mcp__vibe_kanban__create_issue, mcp__vibe_kanban__update_issue, mcp__vibe_kanban__list_sessions, mcp__vibe_kanban__get_issue, mcp__vibe_kanban__add_issue_tag, mcp__vibe_kanban__create_issue_relationship, mcp__vibe_kanban__start_workspace, Read, Glob, Grep
---

This skill will be invoked when the user wants to create a PRD. You may skip steps if you don't consider them necessary.

1. Ask the user for a long, detailed description of the problem they want to solve and any potential ideas for solutions.

2. Explore the repo to verify their assertions and understand the current state of the codebase.

3. Interview the user relentlessly about every aspect of this plan until you reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one.

4. Sketch out the major modules you will need to build or modify to complete the implementation. Actively look for opportunities to extract deep modules that can be tested in isolation.

A deep module (as opposed to a shallow module) is one which encapsulates a lot of functionality in a simple, testable interface which rarely changes.

Check with the user that these modules match their expectations. Check with the user which modules they want tests written for.

5. Once you have a complete understanding of the problem and solution, use the template below to write the PRD. The PRD should be submitted as a Vibe Kanban issue in the **Work** project under the **PRD** column.

<prd-template>

## Problem Statement

The problem that the user is facing, from the user's perspective.

## Solution

The solution to the problem, from the user's perspective.

## User Stories

A LONG, numbered list of user stories. Each user story should be in the format of:

1. As an <actor>, I want a <feature>, so that <benefit>

<user-story-example>
1. As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending
</user-story-example>

This list of user stories should be extremely extensive and cover all aspects of the feature.

## Implementation Decisions

A list of implementation decisions that were made. This can include:

- The modules that will be built/modified
- The interfaces of those modules that will be modified
- Technical clarifications from the developer
- Architectural decisions
- Schema changes
- API contracts
- Specific interactions

Do NOT include specific file paths or code snippets. They may end up being outdated very quickly.

## Testing Decisions

A list of testing decisions that were made. Include:

- A description of what makes a good test (only test external behavior, not implementation details)
- Which modules will be tested
- Prior art for the tests (i.e. similar types of tests in the codebase)

## Out of Scope

A description of the things that are out of scope for this PRD.

## Further Notes

Any further notes about the feature.

</prd-template>

### Propagate Jira URL from Parent Issue

Before creating the PRD issue, extract the Jira URL from the parent Grill issue:

1. Call `mcp__vibe_kanban__list_sessions` **without** `workspace_id` to get the current session data.
2. Extract the `issue_id` from the session.
3. Fetch the parent issue using `mcp__vibe_kanban__get_issue`.
4. Extract the Jira URL from the parent issue's description — look for the pattern `Jira: (https://\S+)`.
5. If found, prepend `Jira: <URL>` as the first line of the PRD description (before the Problem Statement heading).

### Submitting the PRD to Vibe Kanban

After writing the PRD, create a Vibe Kanban issue in the **Work** project under the **PRD** column:

1. **List organizations** using `mcp__vibe_kanban__list_organizations` to get the org ID.
2. **List projects** using `mcp__vibe_kanban__list_projects` with the org ID. Find the project named **"Work"** and note its ID.
3. **Create the issue** using `mcp__vibe_kanban__create_issue`:
   - `title`: A short, label-style title for the feature (e.g., "User auth refactor", "CSV export for reports")
   - `description`: The full PRD text, with `Jira: <URL>` as the first line if a Jira URL was found in the parent issue.
   - `project_id`: The Work project ID from step 2
4. **Move the issue to the PRD column** using `mcp__vibe_kanban__update_issue`:
   - `issue_id`: The issue ID returned from step 3
   - `status`: `"PRD"`
5. **Link the parent Grill issue to the PRD issue** using `mcp__vibe_kanban__create_issue_relationship`:
   - `source_issue_id`: The parent Grill `issue_id` from the session (see "Propagate Jira URL from Parent Issue" above)
   - `target_issue_id`: The PRD issue ID from step 3
   - `relationship_type`: `"related_to"`
6. **Start a PRD-to-Issues workspace** using `mcp__vibe_kanban__start_workspace`:
   - `name`: `"PRD-to-Issues: <SHORT_TITLE>"` — use the same short title from the Kanban issue
   - `executor`: `"CLAUDE_CODE"`
   - `issue_id`: The PRD issue ID from step 3
   - `repositories`: Use repo ID `f1819923-d554-4f4b-a344-6607d6912c59` (core-worktrees) with branch `"main"`
   - `prompt`: `"/kanban-prd-to-issues"`
7. **Tag the parent Grill issue as done** using `mcp__vibe_kanban__add_issue_tag`:
   - `issue_id`: The parent Grill `issue_id` from the session (see "Propagate Jira URL from Parent Issue" above)
   - `tag`: `"done"`

Present a summary to the user:
- The Kanban issue title and ID
- Confirmation that it was placed in the Work project under the PRD column
- The PRD-to-Issues workspace name and status