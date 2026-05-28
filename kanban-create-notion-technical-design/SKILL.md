---
name: kanban-create-notion-technical-design
description: Create a Notion technical design page under the Design Reviews folder. Use when user wants an engineering technical design doc — data models, flows, dependencies, schemas.
allowed-tools: mcp__vibe_kanban__list_sessions, mcp__vibe_kanban__get_issue, mcp__claude_ai_Notion__notion-create-pages, Read, Glob, Grep
---

This skill produces a **technical design** Notion page under the Design Reviews folder. The audience is engineering — data models, flows, schemas, modules, dependencies.

## 1. Resolve the Jira URL (best-effort)

The Jira URL is used for the page title prefix and the first body line. Try, in order:

1. **Current Vibe Kanban session (if running inside a workspace):**
   - Call `mcp__vibe_kanban__list_sessions` **without** `workspace_id` to get the current session.
   - Extract `issue_id` from the session.
   - Fetch the issue using `mcp__vibe_kanban__get_issue`.
   - Look for `Jira: (https://\S+)` in the issue's description.
2. **Already in the conversation:** if the user has already provided a Jira URL or ticket key (e.g. from grilling, the kickoff message, or earlier turns), use that.
3. **Ask the user once:** if neither of the above resolves it, ask the user for the Jira URL or ticket key. They may also say there is none — that's fine.

If no Jira URL is available, continue without it — the title falls back to plain and the `Jira:` body line is omitted.

## 2. Explore the codebase to ground the design

Technical designs need specifics: file paths, table names, function names, module boundaries. Read the repo before drafting. Look for:

- Files and modules the design will touch
- Existing data models / schemas that change
- Current flow / pipeline the design replaces or augments
- Naming conventions in the area you're designing for

**Resolve technical specifics from the codebase before asking the user.** Ask follow-up questions only for decisions the codebase cannot answer (product intent, planned scope, deferred work). If the user has already discussed the design earlier in the conversation (e.g. after a grilling session), lean on that and avoid re-litigating points already settled.

## 3. Draft the design

Use the canonical template below. Sections marked *(conditional)* should be omitted when not applicable — don't pad. Sections marked *(always)* should be present in every design.

<technical-design-template>

Jira: <URL>   ← prepend this as the first line ONLY if a Jira URL was found

## Overview *(always)*

One short paragraph: the problem being solved and the proposed approach at the highest level. Engineering-flavored — assume the reader knows the domain.

## Current State *(conditional — include when there is existing behavior to describe)*

What exists today. Reference real file paths, table names, services. Use a mermaid sequence/flow diagram if the current behavior has non-trivial flow.

## Proposed Design *(always)*

The new approach. Use subsections per major piece (e.g., per scenario, per service, per module). Reference real file paths and module names where they exist in the codebase. Cite the actual repos and files that need to change.

## Data Model *(conditional — include when schemas/tables change)*

Tables, fields, types, relationships. Include a mermaid `erDiagram` when there are relationships between entities. Use SQL DDL or markdown tables for column lists. If the work spans dbt + Temporal (or any dual-pipeline situation), call out both places explicitly.

## Flows *(conditional — include when there are non-trivial flows)*

Sequence diagrams (mermaid `sequenceDiagram`) for each notable flow: discovery, monitoring, analysis, etc. Include the participants (services / queues / tables) and the meaningful steps. Diagrams should match the file/module names used elsewhere in the doc.

## Implementation Plan *(conditional — include when phased rollout matters)*

Phases as a checklist. Each phase: 3–8 bullets. Don't pad — if the work is one PR, skip this section.

## Dependencies *(conditional — include when blocked on other tickets/work)*

Markdown table: dependency, ticket, impact (blocking / parallel / nice-to-have). Be explicit about which scenarios are blocked.

## Out of Scope *(always)*

Bullet list. What this design intentionally does not address, and why (briefly).

## Open Questions *(conditional — include when there are unresolved decisions)*

Numbered list of decisions still pending, with the trade-offs noted where helpful.

</technical-design-template>

### Mermaid diagrams

- **Required** in **Flows** for any non-trivial sequence.
- **Required** in **Data Model** when entities relate to each other (use `erDiagram`).
- Match participant / entity names to what's actually in the codebase.

### Style guidance

- Engineering audience — assume domain knowledge, skip product justification.
- Reference real file paths, table names, function names from the codebase exploration.
- Prefer concrete over abstract: `compute-accounts.sql.ts` beats "the accounts compute step".
- When work spans multiple repos or pipelines, call out **both** explicitly.
- No "Executive Summary" — start with Overview.

## 4. Show the draft and wait for approval

Print the full markdown draft to the user. Ask if they want changes. Iterate until they approve. **Do not create the Notion page until the user explicitly approves the draft.**

## 5. Create the Notion page

Once approved, create the page using `mcp__claude_ai_Notion__notion-create-pages`:

- `parent`: `{ "type": "page_id", "page_id": "1ca0e25bad37803da399e7bcb687ff11" }` — the Design Reviews page (hardcoded).
- `pages`: A single page entry with:
  - `properties`: `{ "title": "<TITLE>" }` — see title format below.
  - `content`: The full approved markdown body. **Do not include the title as a heading at the top** — Notion renders the title separately.
  - `icon`: A relevant emoji chosen from the design's topic. Examples: 🔍 visibility/search, 🔃 monitoring/sync, 🗣️ comms/messaging, 💼 workflows, 🎨 UI, 🔐 auth/security, 📊 analytics, ⚙️ infra/config. Fall back to 📐 if nothing fits well.

### Title format

- **With Jira URL**: `CORE-NNNN — <Short Topic>: Technical Design` (e.g. `CORE-3315 — Multi-Source Visibility for Identities: Technical Design`).
- **Without Jira URL**: `<Short Topic>` plain (matches the older designs in the folder).

The `<Short Topic>` should be label-style — no leading articles, no "as a user...", just the core topic in 3–8 words.

## 6. Report back

Print:
- The created Notion page URL.
- The chosen title and icon.
- A one-line summary of what got created.

Do not modify Vibe Kanban — no issue creation, no tagging, no workspace start. The Notion page is the only artifact this skill produces.
