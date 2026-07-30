---
name: create-design-brief
description: Generates a single-page, self-contained HTML "design brief" — a one-glance technical spec that fits on one scroll: a header (ticket + title + thesis + at-a-glance deltas), a Mermaid ERD / architecture diagram, a 2×2 grid of the design's key dimensions, a worked example (tree + before/after data tables + notes), and an Open/Shipped footer. Dark engineering aesthetic with monospace code chips, blue for structure, violet for the one term that matters. Published as a Claude Artifact so the Mermaid diagram renders natively. Bundles a ready-to-fill template (assets/brief-template.html). Use when the user asks for a design brief / one-pager / ERD brief / spec sheet / "brief like that one", or wants to condense a technical design into a single shareable page. For a multi-slide walkthrough use create-html-presentation instead.
---

# Create Design Brief

## When to use

Trigger when the user wants a **single dense page** that captures a technical
design at a glance — "make a design brief", "one-pager", "ERD brief", "spec
sheet", "a brief like the one we made". The signature is: *everything visible
on one scroll*, anchored by a diagram and a worked example.

Contrast:
- **create-html-presentation** → many slides, click-through, one idea per slide.
- **create-design-brief** (this) → ONE page, dense, scan top-to-bottom. Reach
  for it when the deck would be overkill and the reader wants the whole model in
  a single view.

## The format (keep this order — it's the whole point)

1. **Header** — eyebrow `TICKET · Design Brief`, an `h1` naming the change with
   the single pivotal term in `<span class="model">` (violet), a one/two-sentence
   `.lead` thesis, and `.rel-tags` (4–6 at-a-glance deltas; newest marked `.new`).
2. **Diagram** — a Mermaid `erDiagram` (or `flowchart`) in the `.erd` panel,
   then a one-line mono `.caption` that reads it left-to-right.
3. **Concept grid** — 4 columns (2×2) each a *stable dimension* of the design
   (e.g. Grain / Keys / Linking / Lifecycle). Bulleted, each bullet leads with a
   bold claim; open questions/risks use `.warn`.
4. **Worked example** — ONE concrete entity threaded through a tree + real
   before/after data tables + 3–4 `→` notes answering the obvious reviewer
   questions.
5. **Footer** — `Open:` (unresolved decisions) / `Shipped:` (what's already true).

## Prerequisites

- **Read the source design in full** first — the actual Notion page, design doc,
  or the schema/contract files. The brief must reflect the *current* model, not a
  paraphrase.
- The **ticket id + one-line thesis**.
- The **entities + real columns** for the diagram (grep the Prisma schema / Zod
  models / SQL — PK/FK/nullable annotations must be true).
- **One concrete worked-example entity** that naturally exercises the design
  (a realistic hero, not a toy). If the hero doesn't hit an edge case, add a
  small second row for the outlier rather than faking a sighting.

## Workflow

1. **Read the source in full** (see Prerequisites) and pin the 4 concept
   dimensions + the worked-example entity before writing.
2. **Load the `artifact-design` skill** — required before publishing any
   Artifact; it calibrates the design treatment (this brief is the utilitarian /
   technical end of that spectrum, already realized in the template).
3. **Copy `assets/brief-template.html`** to a working file (the scratchpad dir,
   or a named path). Keep the `<style>` block and the Mermaid `%%{init}%%`
   directive **verbatim** — they are the reusable asset.
4. **Fill the five regions** with real content (see The format + Content
   guidance). Delete the `<!-- ... -->` guide comments as you go.
5. **Publish with the Artifact tool** — pass the file path, a stable `<title>`,
   a one-sentence `description`, and an emoji `favicon`. The Artifact wraps the
   file in `<!doctype><head><body>` and renders the `<pre class="mermaid">`
   block natively. Give the user the returned URL.
6. **Verify** tag balance before publishing (`section`/`div`/`table`/`pre`
   opens == closes) — a malformed row silently breaks the layout.

## Content guidance (what made the original land)

- **Header** — the `h1` states the change, not the feature name; highlight
  exactly ONE term. The `.lead` is a thesis, not a summary. `.rel-tags` are
  deltas ("X on Y", "links move to Z"), not nouns.
- **Diagram** — annotate columns in the Mermaid comment slot (`"NEW"`,
  `"nullable — agent only"`, `"mirrored — dedup key"`); relationship labels
  carry meaning ("global_app_id (all sources)"), never just "has".
- **Concept grid** — 4 dimensions that stay stable as the design evolves. 3–4
  bullets each. Lead bold claim → supporting detail with `<span class="chip">`
  code chips (`.b` blue for the pivotal id, `.a` amber for caution). Park real
  open questions in `.warn` bullets — don't hide the unknowns.
- **Worked example** — this is what turns a schema dump into a story. Show
  *literal rows* (tree + tables), not prose. The `→` notes answer: *how do we
  read X? what about the collision case? what about removal/lifecycle? what's
  the honest interim before dependency Y lands?* Use a `.null` cell to make
  nullable/absent columns visible.
- **Footer** — `Open` is the decisions still owed; `Shipped` is what this safely
  builds on (existing patterns, prod behavior). Both keep the brief honest.

## Critical gotchas

- **Publish as an Artifact, not a standalone file.** Mermaid renders natively in
  Claude Artifacts. A plain `.html` opened in a browser (or committed to a repo)
  will **not** render the ERD — the Artifact CSP blocks Mermaid CDNs. If the user
  needs a repo-committed standalone copy, pre-render the diagram as an inline SVG
  and drop it in place of the `<pre class="mermaid">` block.
- **Artifact file form: no `<!doctype>` / `<html>` / `<head>` / `<body>`.** The
  Artifact tool adds those. The file is just the `<style>` block + `<div class="brief">`.
- **Keep the Mermaid `%%{init}%%` directive verbatim** — it is the dark theme for
  the diagram; without it the ERD renders in Mermaid's default grey.
- **Dark-committed, single theme by design.** This is a deliberate choice for an
  engineering brief (a "terminal" look), not a theme-support omission.
- **Ground everything in the real schema.** Grep the actual Prisma/Zod/SQL before
  writing any entity, column, or example row. Fabricated shapes are the fastest
  way to lose a technical reader — every id and column must be greppable.
- **One highlighted term, one accent story.** Violet only on the `h1` model term
  and the worked-example head; blue carries structure. Don't scatter accents.

## References

- `assets/brief-template.html` — the page to copy and fill (full CSS + Mermaid
  theme + a skeleton demonstrating every component: header, ERD, concept grid,
  worked-example tree + tables + notes, footer).
