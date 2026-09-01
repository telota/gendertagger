# Frontend design guidelines

## Purpose and authority

These guidelines govern the visual and interaction design of the Vue client. They translate the accepted
wireframe ([`23-wireframe-ui-inventory.md`](23-wireframe-ui-inventory.md)) and the decisions recorded in
[`24-frontend-delivery-plan.md`](24-frontend-delivery-plan.md) into rules that can be applied and reviewed.

They are subordinate to the scientific contracts. Where a visual convention would blur a distinction the
pipeline makes — `unknown` against `abstain`, certainty against agreement, a method's confidence against a
calibrated probability — the contract wins and the design changes.

Code-level conventions are in [`26-frontend-coding-guidelines.md`](26-frontend-coding-guidelines.md).
Documentation and naming policy remains [`19-coding-and-documentation-style.md`](19-coding-and-documentation-style.md).

## Principles

1. **Legibility of evidence over visual polish.** A reviewer must be able to see why the pipeline reached a
   decision, not merely what it decided.
2. **Uncertainty is first-class.** Tiers, abstentions, conflicts, and missing evidence get real visual
   treatment. They are never hidden behind an average or a single number.
3. **Provenance is visible on demand.** Hashes, versions, model identifiers, and reviewer attribution are
   always reachable from the artefact they describe, without leaving the screen.
4. **The optional path stays optional.** The game mode is a clearly marked side path, never the default
   entry point, and never influences which records are shown.
5. **Density serves triage.** These screens are worked through in long sessions. Prefer compact, scannable
   rows and stable positions over generous spacing that halves the visible working set.
6. **Nothing is invented.** If a number has no backing contract, it does not appear.

## Color

### Palette

The palette is inherited from the wireframe and is normative. No colour outside these tokens may appear in
the application.

| Role | Token | Value |
|---|---|---|
| Page background | `--page` | `#f2f1ee` |
| Panel background | `--panel` | `#ffffff` |
| Raised surface | `--surface-1` | `#fcfcfb` |
| Primary text | `--text-primary` | `#0b0b0b` |
| Secondary text | `--text-secondary` | `#52514e` |
| Muted text | `--muted` | see [Contrast](#contrast) |
| Hairline / table rule | `--grid` | `#e1e0d9` |
| Border | `--border` | `rgba(11,11,11,0.12)` |
| Navigation accent | `--accent` | `#4a3aa7` |
| Action accent | `--accent-b` | `#0f7a63` |
| Focus ring | `--focus-ring` | `#1f5aa0` |
| Success | `--good` | `#0ca30c` |
| Warning | `--warning` | `#fab219` |
| Critical | `--critical` | `#d03b3b` |

Each canonical label carries three tokens — a solid, a text colour, and a tint:

| Label | Solid | Text | Tint |
|---|---|---|---|
| `male` | `#2a78d6` | `#1f5aa0` | `#e9f1fa` |
| `female` | `#eb6834` | `#b04e27` | `#fdefea` |
| `institution` | `#1baf7a` | `#127a55` | `#e8f7f1` |
| `unknown` | `#eda100` | `#7a5900` | `#fdf5e5` |

The wireframe names this fourth group `--uncertain*`. It is renamed to `--unknown*` per decision D3: it
renders the canonical label `unknown`, and `uncertain` is a certainty tier. Reusing one name for both is the
conflation the published method explicitly warns against.

### Contrast

Measured against WCAG 2.1 AA. These are computed values, not estimates.

| Pair | Ratio | Verdict |
|---|---|---|
| label text on its own tint (`male`) | 6.08 | passes AA text |
| label text on its own tint (`female`) | 4.72 | passes AA text |
| label text on its own tint (`institution`) | 4.82 | passes AA text |
| label text on its own tint (`unknown`) | 5.95 | passes AA text |
| `--text-primary` on `--page` | 17.43 | passes |
| `--text-secondary` on `--panel` | 7.94 | passes |
| `--accent` on `--panel` | 8.56 | passes |
| `--accent-b` on `--panel` | 5.27 | passes |
| `--critical` on `--panel` | 4.80 | passes |
| `--focus-ring` on `--page` | 6.14 | passes |
| label **solid** as text on `--panel` | 2.17–4.42 | **fails** |
| `--muted` `#898781` on `--panel` | 3.59 | **fails AA text** |
| `--warning` as text on `--panel` | 1.83 | **fails** |
| `--good` behind white glyphs | 3.35 | **fails** |

Three corrections follow and are binding:

1. **Solid label colours are fills, borders, and chart marks only.** They never carry text. The
   badge pattern is tint background, solid border, `-text` foreground — which is why the wireframe's badges
   pass while a solid-coloured label would not.
2. **`--muted` is darkened to `#706e68`** (4.51 on page, 5.10 on panel). The wireframe applies `--muted` to
   10–11 px captions, which is the worst case for a failing ratio. If a lighter grey is wanted for
   decoration, introduce a separate non-text token.
3. **Status colours never carry text at their nominal value.** `--warning` takes dark text (`#3a2c00` on
   amber measures 7.43). Where white glyphs sit on `--good`, darken it to `#088a08` (4.52).

### Colour usage rules

- Colour never carries meaning alone. Every label, tier, and status is also distinguishable by text, shape,
  or icon. Roughly one in twelve men has a colour-vision deficiency, and this palette places `male` blue
  next to `female` orange and `institution` green.
- The two accents are not interchangeable. `--accent` marks navigation and current location; `--accent-b`
  marks actions and confirmation.
- Never introduce a colour scale for certainty. Tiers are categorical, not ordinal-continuous — see
  [Rendering the scientific vocabulary](#rendering-the-scientific-vocabulary).
- Charts use the label tokens for label-keyed series only. Any other series uses a neutral ramp.

## Typography

One system stack for interface text, one monospace stack for identifiers, code, and TEI. The wireframe uses
eighteen ad-hoc sizes; they normalise to this scale.

| Step | Size / line height | Use |
|---|---|---|
| `caption` | 11 / 16 | table headers, metadata, pill text |
| `small` | 12 / 18 | secondary rows, helper text, filter labels |
| `body` | 13 / 20 | default interface text, list rows |
| `body-strong` | 14 / 20 | card headings, emphasised rows |
| `title` | 16 / 24 | panel and detail titles |
| `page` | 20 / 28 | screen title, one per screen |
| `display` | 34 / 40 | game mode only |

Weights are 400, 600, and 700 only. Do not introduce intermediate weights or rely on faux bold.

Monospace applies to `tei_id`, GND identifiers, SHA-256 values, version strings, model identifiers, file
names, and TEI snippets. These must be selectable, must not be broken across lines mid-token, and long
values truncate in the middle with a copy affordance rather than at the end — the tail of a hash is as
diagnostic as its head.

## Spacing, radius, and elevation

Spacing is a 4 px scale: 4, 8, 12, 16, 20, 24, 32, 40, 48. The wireframe's intermediate values (5, 7, 9, 13,
18, 26) normalise to the nearest step. No arbitrary pixel values.

Radii: 4 (controls, chips), 8 (inputs, small cards), 12 (cards, panels), 16 (modals), full (pills, dots).

Elevation is used sparingly and only for layers that genuinely float: dropdown menus and modals. Cards and
panels are separated by `--border` and background, not by shadow. One shadow value for menus, one for
modals; no elevation scale.

Motion is limited to state transitions under 150 ms and must respect `prefers-reduced-motion`. No entrance
animations on data, no animated progress beyond the value change itself.

## Rendering the scientific vocabulary

This section is the part of the design system specific to this project. It is normative.

### Canonical labels

Four values, rendered as their English tokens in every locale (decision D3): `male`, `female`, `unknown`,
`institution`. They are the controlled vocabulary written into the TEI output.

`LabelBadge` is the only component that renders a label: tint background, solid 1.5 px border, `-text`
foreground, pill radius. A translated gloss may accompany the token in prose or a tooltip, never inside the
badge.

`null` is not a label. An absent final decision renders as an explicit "no decision" treatment — neutral,
unfilled — never as `unknown`.

### Certainty tiers

Six values from the aggregation, defined in the published method. They describe *how well supported* the
decision is, and they are categorical.

| Tier | Meaning | Treatment |
|---|---|---|
| `high` | ≥ 2 methods voted and ≥ 75 % agreed, or an authority signal fired in agreement | neutral-positive, low visual weight |
| `low` | ≥ 2 voted, agreement ≥ 50 % | warning weight |
| `contested` | ≥ 2 voted, agreement < 50 % | critical weight |
| `single` | only the LLM answered, self-reported high confidence | distinct "thin evidence" treatment |
| `uncertain` | only the LLM answered, self-reported low confidence | distinct "thin evidence" treatment, stronger |
| `no_data` | no method could vote | neutral-empty, clearly not a decision |

`low`/`contested` and `single`/`uncertain` are **different review problems** and must remain visually
distinct: the first is disagreement between methods, the second is absence of corroboration. On the case
study register they are 3.6 % and 12.7 % of entries respectively. A design that merges them into one
"needs attention" bucket buries the contested cases in the larger thin-evidence set.

### Agreement tiers

Six values describing the share of answering methods that voted for the winning label: `unanimous`,
`strong_majority` (≥ 75 %), `weak_majority` (≥ 50 %), `no_consensus` (< 50 %), `single_rater`, `no_answer`.

The wireframe's three-colour consensus dot collapses six values into three and is insufficient. Render all
six, with a shape or glyph difference in addition to colour, and always with an accessible name — the dot
alone is not a label.

Agreement and certainty are related but not the same, and both appear on a review row. Do not use one to
stand in for the other.

### Prediction status

`success`, `abstain`, and `error` are distinct and must look distinct. An abstention means the method had no
usable input; an error means it failed technically; `unknown` is a substantive answer meaning the input was
ambiguous. Rendering an abstention as `unknown` is a contract violation, not a shortcut.

### Authority overrides

When `override_source` is `gnd` or `parenthetical_qualifier`, the pooled vote was superseded. This is the
most decision-relevant fact on a review item and must be visible on the row, not only in the detail panel,
together with how many of the remaining methods agreed with the override.

### Method confidence

Per-method confidence may be shown as method-specific provenance, adjacent to that method's own result, and
must be labelled as such. It must never be:

- averaged or otherwise combined across methods;
- used to sort, rank, or threshold anything;
- rendered as a percentage bar that reads as a calibrated probability;
- shown as a single "confidence" figure for a person or a decision.

The published method records these values but excludes them from the vote. Presenting them as comparable
would assert a property the pipeline does not have.

### Provenance values

Run and method provenance — `code_git_commit`, `config_sha256`, `model_identifier`, `model_checksum`,
`implementation_version`, `normalization_version`, `prompt_version`, snapshot `source_sha256`, export
manifest checksums — render in monospace, truncated with a copy action, and are always attributable to the
artefact they describe.

### Prohibited representations

- A confidence percentage or threshold anywhere in the interface (decision D2).
- A single quality score, star rating, or "accuracy" figure for one person's decision.
- A mean confidence column in the method table.
- Colour as the sole carrier of label, tier, or status.
- Translating canonical labels or tier names.
- Showing a decision without a path to its evidence.

## Layout

The shell is a fixed sidebar plus a content region. One page title per screen. The single breakpoint at
1080 px collapses the sidebar to an icon rail, stacks the workbench columns, and halves the KPI and card
grids; below 720 px the workbench becomes a single column with list and detail as separate views.

The review workbench is the application's primary working surface: a filter column, a list column, and a
detail column. Its geometry is stable — filters do not reflow, and the action bar stays pinned at the bottom
of the detail column so its position never depends on content length. Selecting a row must not shift the
list.

Long collections are cursor-paginated on the server. Never render an unbounded list, and never re-sort or
re-filter a fetched page in the browser.

## Component patterns

**Buttons.** Three variants only — solid (primary action, one per view), ghost (secondary), and plain text
(tertiary/inline). Destructive actions use `--critical` and require confirmation.

**Chips.** Filter chips are toggles and must communicate selected state without relying on colour alone.
A disabled chip states why it is disabled.

**Status pills.** One component with a tone prop covers the wireframe's four separate pill styles.

**Tables.** One component covers the wireframe's four bespoke tables. Headers are `caption` size, uppercase,
`--muted`. Rows use a `--grid` hairline. Wide tables scroll inside their own container; the page never
scrolls horizontally.

**Cards.** Border and background, no shadow. A card has at most one title and does not nest.

**Menus and modals.** Dismiss on outside click and Escape, trap focus while open, and restore focus to the
trigger on close.

**Forms.** Every control has a visible label. Validation messages sit next to the field, state what to do,
and never rely on colour alone. Server-side validation errors from the shared envelope map onto the
originating field where the envelope identifies one.

## Interface states

Every data-bearing view specifies all of these before it is considered designed:

| State | Requirement |
|---|---|
| Loading, first time | Skeleton matching final layout; no spinner-in-empty-box |
| Loading, refetch | Keep current content, mark it stale; never blank an existing view |
| Empty | Explain why it is empty and what action would fill it |
| Error | Message from the error envelope's `code`, plus a retry affordance |
| Partial failure | Bulk operations report per-item outcome; a partial success is never reported as success |
| Async pending | `202`-created resources show their lifecycle (pending → running → terminal) with the resource's own status vocabulary |
| Conflict | `409 annotation_conflict` gets a designed reconciliation view showing both decisions, not a toast |
| Permission | Controls above the user's role are hidden or disabled with a reason, never merely failing on click |

## Accessibility

Target is WCAG 2.1 AA.

- Semantic elements. Interactive things are `<button>` or `<a>`. The wireframe's `div role="button"` pattern
  and its global Enter/Space shim are not carried over.
- Visible focus on every interactive element, using `--focus-ring` at 2 px with a 2 px offset.
- Full keyboard operability, including the review action bar. Single-key shortcuts (1–4) are disabled while
  a text input has focus and are discoverable in the interface, not only in documentation.
- Non-text UI boundaries meet 3:1; text meets 4.5:1. See [Contrast](#contrast) for the three corrections.
- Every status dot, badge, and chart mark has a text alternative. Charts have an accessible table equivalent.
- Live regions announce asynchronous state changes — run progress, save results, conflicts.
- Respect `prefers-reduced-motion`.
- Minimum interactive target 24 × 24 px, with the review action buttons noticeably larger since they are
  used repeatedly at speed.

## Internationalisation and content

German and English from the first milestone (decision D3).

- Canonical labels, tier names, status values, and identifiers are never translated.
- Everything else is. No user-facing string is hard-coded.
- Layouts tolerate roughly 35 % text expansion; German compounds are the common overflow case. Never size a
  control to its English string.
- Dates, times, and numbers are locale-formatted. Timestamps are shown in the viewer's zone with the UTC
  value available; scientific counts and shares keep a stable decimal representation.
- Sentence case for headings and labels; no title case.
- Error text says what happened and what to do next. It does not blame the user, does not expose stack
  traces, request IDs excepted, and does not invent a cause.
- Terminology is fixed per locale in a glossary shipped with the message catalogues, so that "Lauf"/"run",
  "Aggregation", "Redigieren"/"review" stay consistent across screens.

## Design review checklist

A screen is ready for implementation when:

1. every number on it maps to a named field in a delivered contract;
2. all eight interface states are specified;
3. no certainty or agreement value is rendered as a percentage or a score;
4. labels, tiers, and statuses are distinguishable without colour;
5. contrast is verified against the corrected tokens;
6. the keyboard path through the screen is described;
7. both locales fit without truncation or reflow;
8. every displayed decision has a visible route to its evidence and provenance.
