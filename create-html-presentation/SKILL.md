---
name: create-html-presentation
description: Generates a self-contained, single-file HTML slide deck for design reviews and technical presentations — dark modern aesthetic, keyboard navigation, progress bar, and slide counter. Bundles a ready-to-fill template (assets/deck-template.html) and a component catalog (cards, tick lists, tables, flow diagrams, phase roadmaps, two-axis panels, code blocks, pills). Use when the user asks to create or build an HTML presentation / slide deck / design-review deck, wants to turn a plan or design doc into slides, or mentions presentations in this repo. Output goes to presentations/<name>.html.
---

# Create HTML Presentation

## When to use

Trigger when the user wants an **HTML slide deck** — "create a presentation",
"build a deck", "turn this design/plan into slides", "design review deck", or
references the repo's `presentations/` folder. Produces ONE portable `.html`
file (works offline, openable in any browser, emailable). Skip for Markdown
docs, Google Slides, or PDF exports.

## Prerequisites

Inputs to gather from the user:

- The **content/source** (a plan file, design doc, conversation, or bullet
  outline). If it's an existing plan in `.cursor/plans/`, read it in full first.
- A **deck name** (kebab-case → `presentations/<name>.html`).
- Optional: theme tweaks (brand colors, light variant, logo/title text).

## Workflow

1. **Read the source material in full** before writing slides — the deck must
   reflect the *current* state of the plan/design, not a paraphrase.
2. **Copy the template** `assets/deck-template.html` to
   `presentations/<deck-name>.html`. Never start from a blank file — the CSS,
   HUD, progress bar, and keyboard nav must come from the template verbatim.
3. **Author the slides** inside `<div class="deck">`: one `<section class="slide">`
   per idea. First slide carries `class="slide active"`. Aim for ~12-18 slides
   (data-heavy technical reviews legitimately run longer — don't pad or cut to
   hit the range); one concept per slide. Build each from the component catalog
   in `references/slide-components.md` (eyebrow → h2 → cards / ticks / table /
   flow / roadmap / two-axis / code / pills). Lead each slide with an `.eyebrow`
   section label and an `h2` with a one-word `.em` highlight.
   For technical/design reviews, thread one concrete **rolling example**
   through the deck: introduce the example entity early, reuse the *same* entity
   to ground every abstract concept (applicability rules, consolidation,
   state transitions, migration), and show literal **before/after data**
   (old JSON vs new rows) instead of prose — it is what turns a schema dump
   into a story. Don't force one example onto a path it doesn't naturally hit —
   add a **small second example** for the outlier case (e.g. a consolidation
   hero + a separate single-source foil) rather than fabricating an unrealistic
   sighting.
4. **Keep it single-file**: all CSS in the `<style>` block, all JS inline at the
   bottom; no CDN links, no external fonts (the system font stack is already in
   the template), no images unless embedded as data URIs or absolute local paths.
5. **Verify**: confirm tag balance (opening vs closing counts for
   `section` / `div` / `pre` / `table` should match — a quick
   `python3 -c "s=open(...).read(); print(s.count('<div'), s.count('</div>'))"`
   catches a malformed slide faster than eyeballing), check `<section class="slide">`
   count equals `</section>` count, then open it
   (`open -a Safari "presentations/<name>.html"`) and click through. The slide
   counter and progress bar update automatically.

## Critical gotchas

- **Single-file, offline-first.** No external CSS/JS/CDN/web-fonts — a reviewer
  may open it with no network or forward it as an attachment. Use the bundled
  system-font stack and inline everything.
- **Never hardcode the slide total.** The counter and progress bar are computed
  in JS from the live `.slide` node count — just add/remove `<section class="slide">`
  blocks; leave the `<script>` untouched (keep the `→`/`←`/`Space`/`F` handlers).
- **No `any`/`unknown` casts in the nav JS** (repo-wide hard rule). The template
  JS is already strict-clean; keep it that way if you extend it.
- **Ground every schema/JSON example in the real source files** — read the
  actual Zod / Prisma / `.d.ts` definitions before writing any code or payload
  block. Plausible-looking but fabricated JSON ("handwaving") is the fastest way
  to lose the room in a technical review; input/output examples must match the
  shapes a reviewer can `grep` for.

## References

- `assets/deck-template.html` — the deck shell to copy and fill (CSS + chrome + nav JS + sample slides).
- `references/slide-components.md` — copy-paste catalog of every slide component (cards, ticks, tables, flow diagram, roadmap, two-axis, pills, code blocks).
