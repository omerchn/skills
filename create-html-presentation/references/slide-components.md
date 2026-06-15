# Slide component catalog

Copy-paste snippets for building slides inside `assets/deck-template.html`.
Every component relies on the CSS already in the template `<style>` block — do
not redefine classes. Each slide is a `<section class="slide">` (the first one
also gets `active`). Lead each with an `.eyebrow` + `h2` (with one `.em` span).

## Contents

- [Title slide](#title-slide)
- [Cards (2 / 3 up)](#cards)
- [Tick list (status-coded)](#tick-list)
- [Table](#table)
- [Flow / pipeline diagram](#flow-diagram)
- [Phase roadmap](#phase-roadmap)
- [Two-axis comparison](#two-axis-comparison)
- [Code block](#code-block)
- [Pills & badges](#pills)
- [Color & dot conventions](#conventions)

## Title slide

```html
<section class="slide active">
  <div class="eyebrow">SECTION · CONTEXT</div>
  <h1>Main Title<br /><span class="grad-text">Highlighted Part</span></h1>
  <p class="lead" style="margin-top:22px">One-sentence framing.</p>
  <div class="title-meta">
    <div><b>Scope</b>in / out</div>
    <div><b>Surfaces</b>systems</div>
    <div><b>Release</b>when</div>
  </div>
</section>
```

## Cards

`.cols .c2` (two-up) or `.cols .c3` (three-up). Each card: a colored `.dot`
(`d-1`..`d-4`), an `h3`, and a `p`.

```html
<div class="cols c3">
  <div class="card"><h3><span class="dot d-1"></span>Title</h3><p>Body with <span class="chip-code">token</span>.</p></div>
  <div class="card"><h3><span class="dot d-2"></span>Title</h3><p>Body.</p></div>
  <div class="card"><h3><span class="dot d-3"></span>Title</h3><p>Body.</p></div>
</div>
```

## Tick list

Status classes on `<li>`: none (neutral/blue), `good` (green), `warn` (amber),
`bad` (red). Bold the lead-in with `<b>`.

```html
<ul class="ticks">
  <li><b>Neutral.</b> A plain point.</li>
  <li class="good"><b>Resolved.</b> Something that works.</li>
  <li class="warn"><b>Risk.</b> Something to watch.</li>
  <li class="bad"><b>Blocker.</b> A hard problem.</li>
</ul>
```

## Table

Wrap in `.tbl-wrap` for the rounded border. Use `<b>` inside `<td>` to brighten
key cells.

```html
<div class="tbl-wrap">
  <table>
    <thead><tr><th>Field</th><th>Type</th><th>Notes</th></tr></thead>
    <tbody>
      <tr><td><b>sources</b></td><td>string[]</td><td>Product badges.</td></tr>
      <tr><td><b>sourceTypes</b></td><td>enum[]</td><td>AGENT · IDP · IGA.</td></tr>
    </tbody>
  </table>
</div>
```

## Flow diagram

`.flow` wraps `.flow-row`s of `.node`s separated by `.arrow` (`→`) or
`.arrow.down` (`↓`). `.node.accent` highlights a key step; `.node.store` marks a
datastore. `.node .t` is the title, `.node .s` a mono subtitle.

```html
<div class="flow">
  <div class="flow-row">
    <div class="node accent"><span class="t">Discovery WF</span><span class="s">temporal</span></div>
    <span class="arrow">→</span>
    <div class="node"><span class="t">Consumer</span><span class="s">rabbitmq</span></div>
    <span class="arrow">→</span>
    <div class="node store"><span class="t">raw_apps</span><span class="s">snowflake</span></div>
  </div>
</div>
```

## Phase roadmap

`.road` holds three `.phase` panels. Variants `.phase.b` / `.phase.c` recolor
the `.tag`. Bullets are a plain `<ul>` (auto-styled with `›`).

```html
<div class="road">
  <div class="phase"><span class="tag">Phase A</span><h3>Infra</h3><ul><li>Source-agnostic schema</li><li>Ingestion consumer</li></ul></div>
  <div class="phase b"><span class="tag">Phase B</span><h3>Adapt agent</h3><ul><li>Rename workflow</li></ul></div>
  <div class="phase c"><span class="tag">Phase C+</span><h3>Per source</h3><ul><li>One PR each</li></ul></div>
</div>
```

## Two-axis comparison

`.two-axis` holds two `.axis` panels — use `.axis.v` and `.axis.m` for the two
accent tints. `.lab` = uppercase label, `.q` = italic framing question.

```html
<div class="two-axis">
  <div class="axis v"><div class="lab">Level 1</div><h3>COLLECTED</h3><div class="q">"Who sees it?"</div><ul class="ticks"><li>IDP / IGA only</li></ul></div>
  <div class="axis m"><div class="lab">Level 2</div><h3>MONITORED</h3><div class="q">"Who watches it?"</div><ul class="ticks"><li>Agent or mix</li></ul></div>
</div>
```

## Code block

Use `<pre>` with span classes for syntax tint: `.kw` (keyword/purple), `.ty`
(type/green), `.st` (string/amber), `.cm` (comment/faint). Escape `<` as `&lt;`.

```html
<pre><span class="kw">enum</span> <span class="ty">ApplicationSourceType</span> {
  AGENT = <span class="st">'AGENT'</span>,  <span class="cm">// host agent</span>
  IDP = <span class="st">'IDP'</span>,
}</pre>
```

## Pills

Inline status pills: `.pill.a` (amber), `.pill.b` (green), `.pill.new` (blue).
Group in `.badge-row`.

```html
<div class="badge-row">
  <span class="pill new">new field</span>
  <span class="pill a">Snowflake V1</span>
  <span class="pill b">Postgres V2</span>
</div>
```

## Conventions

- **Dots** `d-1` blue, `d-2` purple, `d-3` amber, `d-4` green — keep a stable
  meaning within one deck (e.g. d-1=agent, d-3=IGA).
- **Tick status** green=done/safe, amber=risk, red=blocker, blue=neutral.
- **One idea per slide.** If a slide needs scrolling, split it.
- **`.em` once per `h2`** — highlight the single most important word.
- **`.chip-code` for inline identifiers**, `<pre>` for multi-line code.
