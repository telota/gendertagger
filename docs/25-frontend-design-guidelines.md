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

Both themes ship from the first milestone (decision D8). Tokens are **semantic and theme-scoped**: a
component references `--text-secondary`, never a hex value and never a theme-specific name. Every token
below is defined once per theme, so no component is ever written against a single palette.

The surface and accent palette retains the wireframe's warm archive character. The canonical label
palette approved on 2026-10-03 uses male violet, female teal, unknown gray, and institution ochre.
These tokens are normative; no colour outside them may appear in the application.

| Role                   | Token              | Value                 |
| ---------------------- | ------------------ | --------------------- |
| Page background        | `--page`           | `#f2f1ee`             |
| Panel background       | `--panel`          | `#ffffff`             |
| Raised surface         | `--surface-1`      | `#fcfcfb`             |
| Primary text           | `--text-primary`   | `#0b0b0b`             |
| Secondary text         | `--text-secondary` | `#52514e`             |
| Muted text             | `--muted`          | `#706e68`             |
| Hairline / table rule  | `--grid`           | `#e1e0d9`             |
| Border                 | `--border`         | `rgba(11,11,11,0.12)` |
| Navigation accent      | `--accent`         | `#4a3aa7`             |
| Action accent          | `--accent-b`       | `#0f7a63`             |
| Focus ring             | `--focus-ring`     | `#1f5aa0`             |
| Success                | `--good`           | `#088a08`             |
| Warning                | `--warning`        | `#fab219`             |
| Warning text           | `--warning-text`   | `#7a5900`             |
| Warning tint           | `--warning-tint`   | `#fdf5e5`             |
| Critical fill / border | `--critical`       | `#d03b3b`             |
| Critical text          | `--critical-text`  | `#bf3333`             |
| Critical tint          | `--critical-tint`  | `#fbeceb`             |
| Information text       | `--info-text`      | `#1f5aa0`             |
| Information tint       | `--info-tint`      | `#e9f1fa`             |

Each canonical label carries three tokens — a solid, a text colour, and a tint:

| Label         | Solid     | Text      | Tint      |
| ------------- | --------- | --------- | --------- |
| `male`        | `#7056ad` | `#60458f` | `#f2edf9` |
| `female`      | `#14847d` | `#09665f` | `#e7f4f0` |
| `unknown`     | `#85817a` | `#52514e` | `#f2f1ee` |
| `institution` | `#ae7620` | `#7d530f` | `#faf2e2` |

The wireframe names this fourth group `--uncertain*`. It is renamed to `--unknown*` per decision D3: it
renders the canonical label `unknown`, and `uncertain` is a certainty tier. Reusing one name for both is the
conflation the published method explicitly warns against.

### Dark theme

Derived from the light palette, keeping its warm-neutral cast, and verified to the same standard. Values are
a starting palette: they meet the contrast requirements and may be refined visually, but any refinement is
re-verified before it lands.

| Role               | Light                 | Dark                     |
| ------------------ | --------------------- | ------------------------ |
| `--page`           | `#f2f1ee`             | `#1a1917`                |
| `--panel`          | `#ffffff`             | `#232220`                |
| `--surface-1`      | `#fcfcfb`             | `#2c2a27`                |
| `--text-primary`   | `#0b0b0b`             | `#f4f3f0`                |
| `--text-secondary` | `#52514e`             | `#c2bfb8`                |
| `--muted`          | `#706e68`             | `#9c9890`                |
| `--grid`           | `#e1e0d9`             | `#3a3835`                |
| `--border`         | `rgba(11,11,11,0.12)` | `rgba(244,243,240,0.14)` |
| `--accent`         | `#4a3aa7`             | `#a99bf0`                |
| `--accent-b`       | `#0f7a63`             | `#4fc0a3`                |
| `--focus-ring`     | `#1f5aa0`             | `#8fbdf0`                |
| `--good`           | `#088a08`             | `#4fc94f`                |
| `--warning`        | `#fab219`             | `#f0b843`                |
| `--warning-text`   | `#7a5900`             | `#e8bd5e`                |
| `--warning-tint`   | `#fdf5e5`             | `#332813`                |
| `--critical`       | `#d03b3b`             | `#f0736f`                |
| `--critical-text`  | `#bf3333`             | `#f0736f`                |
| `--critical-tint`  | `#fbeceb`             | `#3d201e`                |
| `--info-text`      | `#1f5aa0`             | `#8fbdf0`                |
| `--info-tint`      | `#e9f1fa`             | `#17293d`                |

Label tokens invert their relationship: the tint becomes a dark, desaturated ground and the text colour
becomes light.

| Label         | Dark solid | Dark text | Dark tint |
| ------------- | ---------- | --------- | --------- |
| `male`        | `#a68ad6`  | `#c5b1eb` | `#30223f` |
| `female`      | `#52bcb0`  | `#7bd3c8` | `#112f2a` |
| `unknown`     | `#9c9890`  | `#c2bfb8` | `#2c2a27` |
| `institution` | `#d6ad58`  | `#e5c078` | `#362b19` |

Measured dark-theme ratios: label text on its own tint 7.62–8.19; `--text-primary` on panel 14.32;
`--text-secondary` 8.66; `--muted` 5.53; `--accent` 6.54; `--accent-b` 7.12; `--critical-text` 5.59;
`--warning` 8.81; `--good` 7.42; focus ring on page 8.96. Label solids as borders on the dark panel measure
5.47–7.55. Critical text also measures 6.18 on page and 5.03 on `--surface-1`; the inverse
`--panel` foreground on a `--critical` destructive button measures 5.59.

Rules specific to the dark theme:

- **Solids are theme-scoped and must not cross over.** The dark solids measure 2.10–2.91 on a white panel
  and fail there; the light solids are dimmer than they should be on a dark panel. A component that
  hard-codes either has a bug.
- Do not render pure white text on pure black. `--text-primary` on `--page` measures 15.83, which is high
  contrast without the halation of `#ffffff` on `#000000`.
- Elevation reads through surface lightness, not shadow: `--surface-1` is _lighter_ than `--panel` in dark
  and _lighter_ than `--page` in light. Shadows stay reserved for menus and modals in both themes and are
  weaker in dark.
- Dark is not a filter. Never derive it with a global CSS `invert()` or opacity overlay; TEI snippets,
  charts, and label colours all break under that approach.

Theme selection follows `prefers-color-scheme` by default, with an explicit three-state user override
(system, light, dark) persisted per account under
[ADR-0043](decisions/ADR-0043-account-level-user-preferences.md). Keep `system` as the saved choice and derive
the effective palette in the browser. The settings form applies a changed choice only after a confirmed
save. Anonymous browser choices remain separate, including the startup theme applied before the session
is known. There is no account startup cache: a resolved account uses system theme while its first
preferences read is pending or unavailable, then applies its canonical saved choice. This can cause a
palette transition after session resolution; it must never reveal another account's saved choice.
Charts, focus rings, and the label palette are all theme-aware; screenshots in documentation state which
theme they show.

### Contrast

Measured against WCAG 2.1 AA. These are computed values, not estimates. The table below is the light
theme; the dark theme's measured values are listed in [Dark theme](#dark-theme). **Both themes are
verified independently** — passing in one proves nothing about the other.

| Pair                                       | Ratio     | Verdict                   |
| ------------------------------------------ | --------- | ------------------------- |
| label text on its own tint (`male`)        | 6.65      | passes AA text            |
| label text on its own tint (`female`)      | 6.04      | passes AA text            |
| label text on its own tint (`unknown`)     | 7.03      | passes AA text            |
| label text on its own tint (`institution`) | 6.05      | passes AA text            |
| critical text on its status tint           | 4.90      | passes AA text            |
| warning text on its status tint            | 5.95      | passes AA text            |
| information text on its status tint        | 6.08      | passes AA text            |
| `--text-primary` on `--page`               | 17.43     | passes                    |
| `--text-secondary` on `--panel`            | 7.94      | passes                    |
| `--accent` on `--panel`                    | 8.56      | passes                    |
| `--accent-b` on `--panel`                  | 5.27      | passes                    |
| `--critical-text` on `--page`              | 4.98      | passes                    |
| `--critical-text` on `--panel`             | 5.62      | passes                    |
| `--critical-text` on `--surface-1`         | 5.47      | passes                    |
| `--panel` text on `--critical` fill        | 4.80      | passes                    |
| `--critical` as text on `--page`           | 4.25      | **fails AA text**         |
| `--focus-ring` on `--page`                 | 6.14      | passes                    |
| label **solid** as text on `--panel`       | 3.88–5.80 | **mixed; use text token** |
| `--muted` `#898781` on `--panel`           | 3.59      | **fails AA text**         |
| `--warning` as text on `--panel`           | 1.83      | **fails**                 |
| `--good` behind white glyphs               | 3.35      | **fails**                 |

The failures are corrections already applied to the token tables above, and the rules behind them are
binding:

1. **Solid label colours are fills, borders, and chart marks only.** They never carry text. The badge
   pattern is tint background, solid border, `-text` foreground. The text tokens pass consistently;
   the solids do not all meet the body-text threshold.
2. **`--muted` is `#706e68`, darkened from the wireframe's `#898781`** (4.51 on page, 5.10 on panel). The
   wireframe applies `--muted` to 10–11 px captions, the worst case for a failing ratio. If a lighter grey
   is wanted for decoration, introduce a separate non-text token rather than relaxing this one.
3. **Status colours never carry text at their nominal value.** `--warning` takes dark text (`#3a2c00` on
   amber measures 7.43). `--good` is `#088a08`, darkened from `#0ca30c` so white glyphs on it reach 4.52.
4. **Critical text uses `--critical-text` on page, panel, and raised surfaces.** The original `--critical`
   passes on the light panel but fails on the page; checking only the panel misses that error. Keep
   `--critical` for fills and borders, including filled destructive buttons with `--panel` foreground.
   The text token has its own role in both themes even where the dark values currently match.

### Colour usage rules

- Colour never carries meaning alone. Every label, tier, and status is also distinguishable by text, shape,
  or icon. This remains necessary with violet, teal, gray, and ochre and their theme-specific variants.
- The two accents are not interchangeable. `--accent` marks navigation and current location; `--accent-b`
  marks actions and confirmation.
- Never introduce a colour scale for certainty. Tiers are categorical, not ordinal-continuous — see
  [Rendering the scientific vocabulary](#rendering-the-scientific-vocabulary).
- Charts use the label tokens for label-keyed series only. Any other series uses a neutral ramp.
  Snapshot source distributions use the corresponding label solid; other or multiple source values
  use a neutral hatch and an explicit separate label, preserving their distinction from `unknown`.
- Charts are hand-rolled SVG against the tokens (decision D10), so they inherit both themes and the label
  palette for free. This covers the distribution bars, the Cohen's κ matrix, and the confusion matrices.

## Typography

One system stack for interface text, one monospace stack for identifiers, code, and TEI. The wireframe uses
eighteen ad-hoc sizes; they normalise to this scale.

Sizes are declared in `rem` so the reader's browser font setting applies. Pixel equivalents assume the
16 px default and are informational only; a component never declares a font size in `px`.

| Step          | Size      | ≈ px | Line height | Use                                        |
| ------------- | --------- | ---- | ----------- | ------------------------------------------ |
| `caption`     | 0.6875rem | 11   | 1.45        | table headers, metadata, pill text         |
| `small`       | 0.75rem   | 12   | 1.5         | secondary rows, helper text, filter labels |
| `body`        | 0.8125rem | 13   | 1.55        | default interface text, list rows          |
| `body-strong` | 0.875rem  | 14   | 1.45        | card headings, emphasised rows             |
| `title`       | 1rem      | 16   | 1.5         | panel and detail titles                    |
| `page`        | 1.25rem   | 20   | 1.4         | screen title, one per screen               |
| `display`     | 2.125rem  | 34   | 1.2         | game mode only                             |

Line heights are unitless so they scale with the step. Spacing that must track text size uses `rem`;
spacing that must stay fixed against the viewport may use `px`.

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

The optional game mode has one scoped exception: its archive otter, saved stamp, floating earned points,
and completion-ticket stars may use one-shot decorative motion up to 800 ms. The otter follows actual
completed-record progress; the stamp appears only after a successful annotation save, and stars only
after the round is persisted. Evidence, focus targets, controls, and scientific labels remain steady.
Reduced motion removes spatial animation and floating points while keeping saved-state text visible.
The transparent cut-paper otter illustration is decorative, uses the same artwork in both themes, and
never encodes labels or scientific status. Surrounding UI uses the existing semantic tokens. See
[`DESIGN.md`](../DESIGN.md#optional-game-mode-character) for the surface direction.

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

Six values from the aggregation, defined in the published method. They describe _how well supported_ the
decision is, and they are categorical.

| Tier        | Meaning                                                                        | Treatment                                    |
| ----------- | ------------------------------------------------------------------------------ | -------------------------------------------- |
| `high`      | ≥ 2 methods voted and ≥ 75 % agreed, or an authority signal fired in agreement | neutral-positive, low visual weight          |
| `low`       | ≥ 2 voted, agreement ≥ 50 %                                                    | warning weight                               |
| `contested` | ≥ 2 voted, agreement < 50 %                                                    | critical weight                              |
| `single`    | only the LLM answered, self-reported high confidence                           | distinct "thin evidence" treatment           |
| `uncertain` | only the LLM answered, self-reported low confidence                            | distinct "thin evidence" treatment, stronger |
| `no_data`   | no method could vote                                                           | neutral-empty, clearly not a decision        |

`low`/`contested` and `single`/`uncertain` are **different review problems** and must remain visually
distinct: the first is disagreement between methods, the second is absence of corroboration. On the case
study register they are 3.6 % and 12.7 % of entries respectively. A design that merges them into one
"needs attention" bucket buries the contested cases in the larger thin-evidence set.

Certainty badge tones use independent status tokens: `contested` uses `--critical-text` and
`--critical-tint`, `low` uses `--warning-text` and `--warning-tint`, and thin evidence uses
`--info-text` and `--info-tint`. They do not borrow canonical label colours. Their gloss inherits
the foreground of the status tint. Text on these tints measures 4.90, 5.95, and 6.08 in light;
5.19, 8.17, and 7.53 in dark.

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

Eligible signed-in sessions use a persistent sidebar plus a content region, with one page title per
screen. Signed-out, unresolved, session-error and password-change-required states use a compact header
with the home brand, account/session controls, and language/theme choices, without an empty sidebar or
drawer trigger. Public legal links remain in the footer. At 1080 CSS px and above, the sidebar follows
the saved expanded/collapsed choice; from 720 to 1079 px it is a compact
rail. Below 720 px a title-bar trigger opens a modal navigation drawer instead of a persistent rail.
The review workbench uses its available content width after the sidebar and page padding, rather than
the viewport breakpoint: three columns need at least 57rem; below that the columns stack in reading order.
Separate mobile list/detail navigation remains part of the V1 view work in the
[improvement plan](27-frontend-improvement-plan.md#v--individual-view-improvements).
`desktop_sidebar_collapsed` records an explicit desktop choice only, defaulting to false. Breakpoint
transitions and temporary mobile/drawer state never change that preference; returning to desktop restores
the saved desktop choice at widths of at least 1080 CSS pixels. The explicit collapsed choice uses the
same icon rail while retaining accessible link names. The expanded choice does not override the narrow
layout. Both the desktop collapse button and personal settings form use
[ADR-0043](decisions/ADR-0043-account-level-user-preferences.md); no separate browser collapse key exists.
The shared navigation model and exact route ownership are specified in
[the delivery plan](24-frontend-delivery-plan.md#contextual-sidebar-completion).

The private header contains short breadcrumbs and an account-name menu for Personal settings and Sign out.
Project switching sits above readable project destinations in the sidebar, including the mobile drawer;
global pages use Projects. [Global header](#global-header) defines ancestry, loading/access states and
composition. Scientific context and task actions remain in each view.
Names wrap; mobile navigation, breadcrumbs, and account controls retain DOM reading order.

The shell uses `--sidebar-width` (15rem), `--sidebar-rail-width` (3.75rem), `--shell-header-height`
(3.5rem minimum), and `--sidebar-transition` (the existing reduced-motion-aware `--motion-state`).
Navigation scrolls independently of the brand and the footer containing language, theme, and the desktop
collapse button. The collapse button is last; its failure/conflict feedback opens upward. Rail destinations and
controls retain accessible names and expose hover/focus tooltips. Expanded desktop and drawer labels
do not repeat in tooltips; unavailable destinations retain their prerequisite explanations. Opening a
menu or changing to a labelled layout dismisses redundant label help. Footer menus open upward. Modal
navigation keeps labels visible, traps focus, and restores it on dismissal; leaving the mobile
breakpoint moves focus to the visible current destination or brand because the title-bar trigger hides.

The review workbench is the application's primary working surface: a filter column, a list column, and a
detail column. Keep selection from shifting the list. The shared containment foundation uses shrinkable
grid/flex children and wrapping identifiers. `--page-gutter` caps horizontal padding at 4vw on narrow
screens while retaining the normal four-step inset on wider screens. Shared fact lists use
`.app-fact-list` and `.app-fact-list__item`: labels stack above values below a 24rem container width;
wider lists use an overridable 9rem label track and a shrinkable value track. Review-specific navigation
and decision placement are resolved in V1.

**Page conventions.** Each route owns one H1; panels use subordinate headings. Keep the route's heading
available during loading and errors when its identity is already known. API-derived titles must not
invent an unresolved resource name. Existing views that omit their heading while loading are tracked
in their V-family pass; shell focus does not depend on a heading being ready.

Keep the primary task action beside the page heading or the form/record it affects; row and bulk actions
stay with their targets. On narrow screens, actions wrap after the heading or form in the same reading
and keyboard order. Do not move a route-specific command into the global header to save page space.
Use one solid primary action per task context, with secondary recovery/navigation actions subordinate.

Choose content width by task: ordinary project workflows use the same 60rem page frame as Projects,
Members, Runs, and Overview. Comparison tables stay within that frame and use shrinkable tracks plus
local table scrolling. Workbenches and genuinely wide administrative directories may use a different
named width. Do not create a one-off page width to preserve an incumbent layout; use shared gutters and
containment patterns, and preserve the user's entered data and selection on reflow.

Use the named CSS recipes in `src/styles/layout.css` for repeated geometry. Every page-owning `main` uses
`.app-page-frame` for containment, the shared gutter, and the ordinary 60rem project-workflow width.
Reading pages use `.app-page-frame--reading` (40rem), authentication uses `--auth` (24rem), the personal
settings form uses `--form` (48rem), and raw method results use `--wide` (76rem). Only the review and
snapshot-annotation workbenches use `.app-page-frame--dense`; it removes the width cap and reduces block
padding without changing the horizontal gutter. Feature-local root rules do not override frame width or
outer padding.
`.app-page-heading` and its `__copy`, `__title`, `__description`, and `__actions` elements keep page
identity before actions and allow the row to wrap in DOM order. `.app-form-actions` gives every disclosed
creation form a full-width, wrapping action row aligned to the inline end; keep secondary actions before
the primary commit in DOM order. `.app-card` is the default boundary for
top-level page content, task forms, reports, and statistics. `.app-resource-card` is the same flat
geometry with a semantic name for repeated domain resources. Both own only panel, border, radius,
four-step padding, and overflow protection; feature CSS still owns internal grid or flex topology.
`.app-card--sectioned` removes the outer inset so full-width child sections can each apply that standard
inset. `.app-multiline-field` gives native textareas the standard field surface, invalid border, and
vertical resize behavior. Do not introduce feature-local card padding variants.

Long collections are cursor-paginated on the server. Never render an unbounded list, and never re-sort or
re-filter a fetched page in the browser.

### Global header

The header shows where the user is within the current project or application, while keeping account
access and mobile navigation available. It does not own the page's task or scientific context. This is an
operational surface: success means correct orientation and predictable access during work.

| Content                                                  | Owner and behavior                                                                                                                                                                     |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Location                                                 | Private navigation uses breadcrumbs for the authorized project or application destination. Public pages use the home brand and their own page heading.                                 |
| Project switching                                        | Sidebar, above project destinations, on readable project routes. Global pages use Projects.                                                                                            |
| Account identity                                         | Header button shows the full display name; its menu contains Personal settings and Sign out.                                                                                           |
| Mobile navigation                                        | Eligible signed-in sessions get the sidebar drawer trigger. Public sessions have no empty drawer.                                                                                      |
| Product identity                                         | Sidebar brand for private navigation; a header home link names `gendertagger` for public/session-access pages.                                                                         |
| Language, theme, desktop collapse                        | Eligible sessions use the sidebar footer. Public/session-access pages keep language and theme in a compact header; collapse is unavailable there. Preference persistence is unchanged. |
| Page title, filters, actions, editable inputs            | Relevant view; one H1 per page.                                                                                                                                                        |
| Snapshot, run, aggregation, evaluation/export provenance | Relevant view; no persistent scientific identifier chain in the header.                                                                                                                |
| Person and annotation context                            | Review/person detail keeps TEI identity, evidence, decisions and history together.                                                                                                     |
| Working aggregation                                      | Project overview owns selection (ADR-0035); task pickers mark it as recommended without automatic selection. Scientific task context stays in the selected view.                       |
| Session initialization, retry and logout failure         | Header account area; existing recovery dialog owns mid-task authentication.                                                                                                            |
| Progress, save errors, conflicts and partial results     | The view or control performing the operation.                                                                                                                                          |

Do not add search, notifications, a job centre, a status summary, an avatar or a project selector to the
header. Account settings remain distinct from administrative branding settings.

**Breadcrumbs.** Use real navigable ancestry, limited to resources already identified by the route.
Ancestors are links; the current destination is ordinary text with `aria-current="page"`. Separators are
decorative. Names wrap, including long German project and account names, without requiring hover to read
them.

| Route family                                    | Breadcrumb example                                                               |
| ----------------------------------------------- | -------------------------------------------------------------------------------- |
| Signed-in global destination                    | Projects, Personal settings, Accounts, Legal notice, or the relevant destination |
| Project overview                                | Full project name                                                                |
| Review, people, import, aggregation, membership | Project name › Current destination                                               |
| Snapshot runs, evaluations, exports             | Project name › Current collection                                                |
| Run detail                                      | Project name › Runs › Run                                                        |
| Evaluation/export detail                        | Project name › Evaluations/Exports › Evaluation/Export                           |
| Management-only membership                      | Projects › Project membership                                                    |

The run parent comes from the route's snapshot identifier; evaluation/export parents use its run
identifier. Review and aggregation routes do not fetch a run or snapshot merely to lengthen the trail.
Resource identifiers remain with their view. Breadcrumbs supplement the sidebar's primary navigation;
they do not add a second row of tabs or replace the page heading. Breadcrumb and project-switch
navigation honour the shared [draft-leave guard](26-frontend-coding-guidelines.md#routing).

**Project identity and switching.** Project identity uses the route `projectId` and the existing
principal-scoped `useProject` query. Only a successful matching response with a readable project role
supplies the name. The header and sidebar share this source. A new route/account, pending request or
failed query cannot display a previous project's name. A transient failure offers Retry;
forbidden/missing context offers Projects without inferring why the API denied access. A management-only
membership route retains generic scope and does not imply that membership access itself failed. On the
membership route, the shared membership-state read establishes management authority and any ordinary
project role before the shell requests readable project identity. Management alone exposes a Members
destination without scientific project navigation. Members has its own active state; it never
highlights Overview. No managed-project pagination is added for decoration.

The current project's name is the switcher button's visible label. This single control combines
project identity and switching above its destinations, replacing the separate name, action row, and
"Current project" heading. Its accessible name explains switching and includes the current project.
Project alternatives use the first server-ordered page of `useProjectList`, with loading, empty and
retry states. The Projects destination directly above the switcher opens the full list; the quick menu
does not duplicate that link. A failed alternatives read does not erase the separately authorized
current name. Switching opens the target project's overview without transferring old filters or resource
IDs. The menu is bounded by the viewport and repositions on scrolling/resizing. Desktop renders its popup
through a body portal so the sticky sidebar cannot trap it beneath page content. Mobile retains the
popup inside the drawer's focus boundary. Crossing into mobile closes the desktop popup. The collapsed
rail uses an accessible icon button and project-naming tooltip.

**Session states.** Session resolution, anonymous, failed initialization, password-change-required, and
ready states remain distinct. Private controls wait for an eligible session. Forced password change keeps
account identity and Sign out available. Logout failures keep the current account and unsaved input
visible with Retry; only confirmed logout or an already-anonymous response clears the session. Late
responses must not clear a replacement session or redirect its user. Principal changes close
account/project overlays and clear prior-account input. Same-account recovery preserves eligible drafts.

**Composition.** An eligible session (`canUsePrivateNavigation`) uses the sidebar and breadcrumb header.
Signed-out, unresolved, failed-session and password-change-required states use the full content width
without a sidebar or drawer trigger. Their header contains the home brand, account/sign-in/session
feedback and the existing preference controls in a compact horizontal presentation. On the signed-out
home page, an inline sign-in form (username, password, submit; success continues to the projects, or to
the forced password change) replaces the header link, and the header omits its duplicate link and empty
account slot. The login page omits the header link as well. Other public pages retain the header sign-in
entry, and session loading/error feedback remains available on every route. At narrow widths the
preferences wrap into a full-width second row. Menus open downward; temporary and anonymous preference
behavior is unchanged. Login restores private navigation, and logout removes it without changing the
saved desktop-collapse preference.

For private navigation, desktop uses breadcrumbs followed by the account control. Narrow screens use
navigation and breadcrumbs in the first row, with the account control beneath. The DOM and reading order
agree. Menus, failures and long labels can wrap; the header is not sticky. The project switcher moves
with the sidebar into its mobile drawer.

**Verification.** Automated verification covers both locales, route ancestry, long names,
loading/retry/access loss, principal changes, menu semantics, drawer placement, session failures and
draft navigation. Rendered desktop/mobile geometry, enlarged text, keyboard visibility and
assistive-technology checks remain required; component tests do not substitute for them. Outstanding
live checks are recorded in the [improvement plan](27-frontend-improvement-plan.md).

## Component patterns

**Buttons.** Three variants only — solid (primary action, one per view), ghost (secondary), and plain text
(tertiary/inline). Destructive actions use `--critical` fills and borders, `--critical-text` for ghost
and text variants, and require confirmation. Filled variants keep `--panel` text in both themes.
Shared buttons, text fields, single-line native inputs/selects, and listbox/project-switcher triggers and
options use `--control-min-size`: 2rem normally, increasing to `--control-touch-size` (2.75rem) below
720 CSS px or when any pointer is coarse. At the default root size these are 32px and 44px. Compact
variants retain that minimum. Standalone drawer/menu buttons use the touch minimum. Checkboxes, radios,
file inputs, multiline controls, and noninteractive badges retain their own geometry; their surrounding
labels and spacing remain part of each view's accessibility check.

**Chips.** Filter chips are toggles and must communicate selected state without relying on colour alone.
A disabled chip states why it is disabled.

**Status pills.** One component with a tone prop covers the wireframe's four separate pill styles.

**Tables.** One component covers the wireframe's four bespoke tables. Headers are `caption` size, uppercase,
`--muted`. Rows use a `--grid` hairline. Wide tables scroll inside their own container; the page never
scrolls horizontally. Use `AppScrollRegion` with a localized name distinct from enclosing landmarks.
It adds a keyboard tab stop and a visible, associated horizontal-scroll hint only while content overflows,
remeasures when the region or its slotted content changes size, and preserves the table's semantics.
The current consumers are review method evidence, the account directory, and the branding-value table.
Keep an intentional table minimum width where shrinking would make columns unreadable; a future stacked
record presentation is a view decision rather than a global overflow workaround.

**Cards.** Border and background, no shadow. Put each major content, task, report, or statistics region
in one card; keep page identity, breadcrumbs, and collection headings outside. A card has at most one
title and never contains another full card. Separate its inner groups with dividers or closed
disclosures instead of adding another border, radius, and inset.

**Menus and modals.** Built on the headless accessibility library chosen in decision D9 — menus, modals,
listboxes, and tooltips take their behaviour and focus management from it and their appearance from the
project tokens. Clamp popup minimum widths to their available width as well as setting maximum widths;
enlarged text must not force a minimum wider than the screen. The sidebar project menu is bounded by the
viewport and repositions on scrolling/resizing. Desktop portals the popup outside the sticky sidebar
stacking context; mobile keeps it inside the dialog. Crossing into mobile closes the desktop popup.
The account menu opens below the wrapping header. Dismiss menus on outside click and Escape and
restore trigger focus;
modal dialogs trap focus. Use the library behavior; do not accept its visual defaults.

**Forms.** Every control has a visible label. Validation messages sit next to the field, state what to do,
and never rely on colour alone. Server-side validation errors from the shared envelope map onto the
originating field where the envelope identifies one. Shared single-line controls may shrink to their
container; fieldsets have no intrinsic minimum inline size and legends wrap. These rules prevent a long
label or translated legend from forcing the document wider than the screen.

## Interface states

Use `AppFeedback` for reusable inline feedback layout: wrapping message content and a separate actions
slot for retry/recovery controls. The caller supplies translated copy, decides state and recovery, and
retains any intentional focus target. The primitive neither fetches nor retries, infers permission,
aggregates partial outcomes, nor owns scientific status vocabulary.

Route-level loading, empty, failure, and recovery feedback is a structural region and therefore uses
the shared card boundary. Feedback already contained by a card stays inline; never add another card
inside it merely to display a message.

Choose announcement urgency explicitly: `off` for static explanations such as view-only permission,
`polite` for loading/progress/saved summaries, and `assertive` for failures requiring attention. Visual
critical tone is independent of urgency and uses `--critical-text`; do not encode meaning through colour
alone. Keep changing status/error regions mounted where possible so updates use the same live region.
Put recovery controls in the actions slot, outside the announced message, and avoid nested live regions.
Loading announcements complement a view's skeleton or retained data rather than replacing that layout.

Conflict reconciliation keeps its resource-specific comparison, revision, explicit reload, and focus
behavior. Bulk summaries retain individual saved/skipped/conflict/failure outcomes. Adopt the shared
presentation in remaining view families when it improves consistency; do not erase those distinctions
or wrap existing purpose-built focus targets merely to make all markup identical.

Every data-bearing view specifies all of these before it is considered designed:

| State               | Requirement                                                                                                           |
| ------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Loading, first time | Skeleton matching final layout; no spinner-in-empty-box                                                               |
| Loading, refetch    | Keep current content, mark it stale; never blank an existing view                                                     |
| Empty               | Explain why it is empty and what action would fill it                                                                 |
| Error               | Message from the error envelope's `code`, plus a retry affordance                                                     |
| Partial failure     | Bulk operations report per-item outcome; a partial success is never reported as success                               |
| Async pending       | `202`-created resources show their lifecycle (pending → running → terminal) with the resource's own status vocabulary |
| Conflict            | `409 annotation_conflict` gets a designed reconciliation view showing both decisions, not a toast                     |
| Permission          | Controls above the user's role are hidden or disabled with a reason, never merely failing on click                    |

## Accessibility

**Target is WCAG 2.2 AA.** The application is built for a public-sector body, so conformance is a legal
obligation rather than a quality goal; the applicable regime and its evidence requirements are decision D15
in [`24-frontend-delivery-plan.md`](24-frontend-delivery-plan.md). Whatever regime applies references
EN 301 549, which in turn references WCAG, so building to the current 2.2 level satisfies any of them.

- Semantic elements. Interactive things are `<button>` or `<a>`. The wireframe's `div role="button"` pattern
  and its global Enter/Space shim are not carried over.
- A localized skip link is the shell's first keyboard stop and becomes visible on focus. It focuses a
  stable routed-content wrapper without changing the URL; individual views retain their main landmark.
- After a confirmed pathname change, focus that same wrapper once after rendering and navigation-drawer
  dismissal. Initial application loading, query/hash changes, cancelled navigation, and background data
  updates preserve focus. An open modal retains focus ownership. Do not wait for async headings and
  then move focus a second time; loading/error content must also have a usable destination.
- Visible focus on every interactive element, using `--focus-ring` at 2 px with a 2 px offset.
- Full keyboard operability, including the review action bar. Single-key shortcuts (1–4) are disabled while
  a text input has focus and are discoverable in the interface, not only in documentation.
- Non-text UI boundaries meet 3:1; text meets 4.5:1. See [Contrast](#contrast) for the token corrections.
- Every status dot, badge, and chart mark has a text alternative. Charts have an accessible table equivalent.
- Live regions announce asynchronous state changes — run progress, save results, conflicts.
- Respect `prefers-reduced-motion`.
- Minimum interactive target 24 × 24 CSS px (2.5.8), with the review action buttons noticeably larger since
  they are used repeatedly at speed.
- Content reflows without horizontal scrolling down to 320 CSS px width, equivalently at 400 % zoom (1.4.10),
  and survives the text-spacing overrides of 1.4.12. The three-column workbench collapses rather than
  compressing.
- Nothing the user focuses is obscured by sticky furniture (2.4.11). The review workbench's pinned action bar
  is the specific risk: the focused list row must never end up behind it.
- No interaction depends on dragging (2.5.7). Anything draggable also has a keyboard and click equivalent.
- Help and navigation stay in a consistent place across screens (3.2.6), and information already given is not
  demanded again within a flow (3.3.7).
- Authentication does not rely on a cognitive function test (3.3.8): password managers, autofill, and paste
  must work. The local account provider chosen in decision D1 asks only for a username and password, so
  the requirement rests on the login and password-change forms: neither may block paste or autofill.
- Time limits are adjustable, extendable, or switchable off (2.2.1). Session expiry
  falls under the criterion's 20-hour exception, because every session limit exceeds 20 hours
  ([ADR-0032](decisions/ADR-0032-sliding-session-lifetime.md)), so no pre-expiry warning is required; an
  expired session must still never silently discard an unsent decision.
- The game-mode timer is switchable off per decision D19: the control is reachable **before the first timed
  round starts**, the choice persists, and the timer imposes no limit or scoring consequence. Disabling it
  changes nothing about which records are shown or how the annotation is written.
- Status messages use the correct role so they are announced without stealing focus (4.1.3).

The wireframe is explicitly not a reference for interaction markup. Its 90 `div role="button"` constructs,
its non-semantic toggles, slider, and checkboxes, its unhidden decorative glyphs, and its incomplete tab
pattern are all replaced rather than ported. See
[`24-frontend-delivery-plan.md`](24-frontend-delivery-plan.md).

## Publication details, footer, and legal notice

The client is a digital publication and has to follow the operating institution's guideline for digital
scientific resources, which asks for bibliographic, administrative, and legal information in fixed places.
For this deployment that is the BBAW guideline "Leitlinien Startseite und Footer", kept in the academy's
internal team wiki and deliberately not linked here, because these documents ship with the package. Ask
TELOTA for the current version, and compare it with this section whenever the guideline changes.

Every value below is deployment configuration, not frontend source code:
[ADR-0036](decisions/ADR-0036-institution-branding-configuration.md) has the backend read it from
operator-supplied settings and serve it over `GET /api/v1/branding`, so the same built image serves any
institution. The table restates the guideline's requirements in the project's own words and records the
values **this deployment** configures; another deployment sets its own.

| Guideline item                                                     | Where                                                                     | This deployment's configured value                                                                                                                                                                                                                                                |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Title, editors, publisher, and publication period, clearly visible | Title in the start-page content; publication details in the shared footer | Editors: Frederike Neuber, Lou Klappenbach, Tim Westphal, taken from the published paper and still to be confirmed. Period: "since 2026", to be confirmed.                                                                                                                        |
| Citation hint, DOI or URN                                          | Start page                                                                | Omitted until the resource has an identifier and a stable public address                                                                                                                                                                                                          |
| Publisher, by logo or name, on every page                          | Footer                                                                    | The BBAW as text, plus its logo once the team supplies the official file to mount at `branding.logo_path`                                                                                                                                                                         |
| Funders                                                            | Footer                                                                    | None: the application has no external funding. If that changes, the guideline's funder block is added.                                                                                                                                                                            |
| Institutional context                                              | Shared footer, including the start page                                   | Linked by name via `branding.initiatives`: "KI-Lab bei TELOTA" (`https://www.bbaw.de/bbaw-digital/ki`) and "Gender & Data" (`https://gender-data.bbaw.de/`), labelled "Entstanden im Rahmen von" and "Developed within". Initiative names are proper names and stay untranslated. |
| Contact, and technical notes                                       | Footer                                                                    | One address, `telota@bbaw.de`, serves both                                                                                                                                                                                                                                        |
| Licence, with a link to its text                                   | Footer                                                                    | Source-code licence (MIT), which has no version. This is a fact about the software, not deployment configuration, and stays a frontend constant.                                                                                                                                  |
| Privacy notice of the operating institution                        | Footer link                                                               | `https://www.bbaw.de/datenschutz`                                                                                                                                                                                                                                                 |
| Legal notice                                                       | Footer link to `/impressum`                                               | Modelled on `https://www.bbaw.de/impressum/`; see below                                                                                                                                                                                                                           |

**Publication section.** The shared footer groups editors, publisher, initiatives, and publication period
under one heading. These facts appear once on each page, with contact, source-code licence, and legal
links in a separate row beneath them. The layout uses flat surfaces, existing type and spacing tokens,
and wrapping columns that stack on narrow screens. A successful empty response shows the unconfigured
message; a failed read shows a distinct error. Loading does not imply missing configuration. Licence and
legal navigation remain available in every state.

**Legal notice.** It is a public route, reachable without a session, so it is exempt from the authentication
requirement. Its sections follow the BBAW notice: provider and legal form, address, telephone, representative,
and VAT identification number; responsibility and contact (TELOTA); copyright and licence; liability; privacy.
It also states that the gender annotations the application produces are machine suggestions that need editorial
review. The provider values come from `branding.legal_entity` (ADR-0036) and are not recorded in this
document. A field the operator has not configured renders as an explicit "not configured" state, never as
invented text. For this deployment, the BBAW values and their wording need confirmation by the BBAW
administration before `branding.legal_entity` is set for a public deployment.

**Contact address.** The guideline replaces the project address with the function address of the academy's
administration after the project ends. The Gender & Data initiative runs from April 2026 to April 2028, so
this deployment's `branding.contact_email` has to be reviewed before that date.

**Licence scope.** The footer licence covers the application's source code and is the same for every
deployment, so it is not part of `branding` configuration. Register data imported into a project stays under
the licences of its edition, and the legal notice says so. A licence for content or data needs its own entry
chosen under the applicable licensing guideline, with the version, a link to the licence text, and the licence
icon.

**Publisher logo.** Logos are official brand assets. An operator mounts the file into the backend container
and points `branding.logo_path` at it; the footer shows it as a decorative image beside the publisher's name
only once `GET /api/v1/branding` reports a `logo_url`.

**Privacy.** The footer links the operating institution's general privacy notice. The application sets a
session cookie and a CSRF cookie at login ([ADR-0031](decisions/ADR-0031-local-database-authentication.md)), so
whether a given deployment needs a privacy statement of its own is a question for that institution's data
protection officer.

**Facts and wording are separate.** Names, addresses, identifiers, and URLs are operator-configured data
served by the backend (ADR-0036); the surrounding text is in the frontend's message catalogues and is
translated. Each fact then has exactly one source, and none of it is a frontend constant.

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

Authenticated locale selection is account-owned under
[ADR-0043](decisions/ADR-0043-account-level-user-preferences.md): German, English, or browser default.
Browser default remains null in the resource and is resolved by the browser to the first supported primary
language subtag, then German. This changes persistence only; untranslated scientific vocabulary and
catalogue rules from ADR-0030 remain unchanged. Anonymous browser language and theme choices remain
available in the compact header when signed out and are restored after logout without copying account
choices into browser storage. Eligible signed-in sessions keep those controls in the sidebar footer
(inside the navigation drawer on mobile). Both presentations use the same preference component and
preserve temporary nonpersistent choices while session access is unresolved.

## Personal settings

The lazy `/settings` page is named `userSettings` and is discoverable through the translated Personal
settings item in the header account menu. Every signed-in, password-current user
can open it independently of project or global role. Signed-out and forced-password states follow the
existing authentication flow. Administrative branding remains a separate screen at `/admin/settings`.

Keep the form focused on three labelled controls: Interface language (Browser default, Deutsch, English),
Theme (System, Light, Dark), and Desktop sidebar (Expanded, Collapsed). Use the existing native/headless
control patterns, semantic tokens, and German/English catalogues. A short description distinguishes the
saved desktop choice from responsive layout. Keep controls and actions usable with German expansion and
at narrow widths; hidden sidebar labels remain available to assistive technology.

Save is explicit. Draft edits and Restore defaults change only local form state until saving succeeds.
Provide clear unsaved, saving, and saved states with accessible status announcements. Loading and read
failure/retry precede the form; save failures retain entered values. A conflict clearly explains that
saved values changed elsewhere and offers a deliberate reload of saved values; never silently overwrite
or replay the draft. Apply locale, theme, and desktop collapse from the canonical server response only.

## Design review checklist

A screen is ready for implementation when:

1. every number on it maps to a named field in a delivered contract;
2. all eight interface states are specified;
3. no certainty or agreement value is rendered as a percentage or a score;
4. labels, tiers, and statuses are distinguishable without colour;
5. contrast is verified in **both themes** against the corrected tokens;
6. the keyboard path through the screen is described, including focus order and what is announced;
7. both locales fit without truncation or reflow, in both themes;
8. every displayed decision has a visible route to its evidence and provenance;
9. it reflows to 320 CSS px without horizontal scrolling, and no sticky element can obscure the focused
   control.
