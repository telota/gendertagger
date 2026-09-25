---
version: alpha
name: gendertagger
description: A compact bilingual scholarly workbench for evidence-led review and reproducible annotation.
colors:
  quiet-parchment: "#f2f1ee"
  paper-panel: "#ffffff"
  raised-paper: "#fcfcfb"
  primary-ink: "#0b0b0b"
  secondary-ink: "#52514e"
  muted-ink: "#706e68"
  grid-line: "#e1e0d9"
  border-line: "rgba(11, 11, 11, 0.12)"
  annotation-ink: "#4a3aa7"
  registry-teal: "#0f7a63"
  focus-blue: "#1f5aa0"
  verified-green: "#088a08"
  caution-gold: "#fab219"
  critical-red: "#d03b3b"
  overlay-backdrop: "rgba(11, 11, 11, 0.4)"
  male-blue: "#2a78d6"
  male-blue-text: "#1f5aa0"
  male-blue-tint: "#e9f1fa"
  female-coral: "#eb6834"
  female-coral-text: "#b04e27"
  female-coral-tint: "#fdefea"
  institution-green: "#1baf7a"
  institution-green-text: "#127a55"
  institution-green-tint: "#e8f7f1"
  unknown-amber: "#eda100"
  unknown-amber-text: "#7a5900"
  unknown-amber-tint: "#fdf5e5"
  night-quiet-parchment: "#1a1917"
  night-paper-panel: "#232220"
  night-raised-paper: "#2c2a27"
  night-primary-ink: "#f4f3f0"
  night-secondary-ink: "#c2bfb8"
  night-muted-ink: "#9c9890"
  night-grid-line: "#3a3835"
  night-border-line: "rgba(244, 243, 240, 0.14)"
  night-annotation-ink: "#a99bf0"
  night-registry-teal: "#4fc0a3"
  night-focus-blue: "#8fbdf0"
  night-verified-green: "#4fc94f"
  night-caution-gold: "#f0b843"
  night-critical-red: "#f0736f"
  night-overlay-backdrop: "rgba(0, 0, 0, 0.6)"
  night-male-blue: "#5a9ee8"
  night-male-blue-text: "#8fbdf0"
  night-male-blue-tint: "#17293d"
  night-female-coral: "#f08055"
  night-female-coral-text: "#f0a184"
  night-female-coral-tint: "#3a1e14"
  night-institution-green: "#35c894"
  night-institution-green-text: "#6fd6ae"
  night-institution-green-tint: "#102e24"
  night-unknown-amber: "#e8b53c"
  night-unknown-amber-text: "#e8bd5e"
  night-unknown-amber-tint: "#332813"
typography:
  caption:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 400
    lineHeight: 1.45
  small:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.5
  body:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.55
  control:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 600
    lineHeight: 1.55
  body-strong:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.45
  title:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.5
  page:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.4
  display:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif"
    fontSize: "2.125rem"
    fontWeight: 700
    lineHeight: 1.2
  mono-data:
    fontFamily: "ui-monospace, 'SFMono-Regular', Menlo, Consolas, 'Liberation Mono', 'Courier New', monospace"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  control: "4px"
  input: "8px"
  card: "12px"
  modal: "16px"
  full: "9999px"
spacing:
  step-1: "0.25rem"
  step-2: "0.5rem"
  step-3: "0.75rem"
  step-4: "1rem"
  step-5: "1.25rem"
  step-6: "1.5rem"
  step-8: "2rem"
  step-10: "2.5rem"
  step-12: "3rem"
components:
  button-solid:
    backgroundColor: "{colors.registry-teal}"
    textColor: "{colors.paper-panel}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "0.5rem 1rem"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.primary-ink}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "0.5rem 1rem"
  button-text:
    backgroundColor: "transparent"
    textColor: "{colors.annotation-ink}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "0.25rem 0.5rem"
  text-field:
    backgroundColor: "{colors.paper-panel}"
    textColor: "{colors.primary-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.input}"
    padding: "0.5rem 0.75rem"
  compact-listbox:
    backgroundColor: "{colors.paper-panel}"
    textColor: "{colors.primary-ink}"
    typography: "{typography.small}"
    rounded: "{rounded.control}"
    padding: "0.25rem 0.75rem"
  project-card:
    backgroundColor: "{colors.paper-panel}"
    textColor: "{colors.primary-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.card}"
    padding: "1rem"
  nav-active:
    backgroundColor: "{colors.raised-paper}"
    textColor: "{colors.annotation-ink}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.control}"
    padding: "0.5rem 0.75rem"
  vocabulary-badge:
    backgroundColor: "{colors.female-coral-tint}"
    textColor: "{colors.female-coral-text}"
    typography: "{typography.mono-data}"
    rounded: "{rounded.full}"
    padding: "0 0.5rem"
  review-row-selected:
    backgroundColor: "{colors.raised-paper}"
    textColor: "{colors.primary-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.card}"
    padding: "0.5rem 0.75rem"
---

# Design System: gendertagger

## Overview

**Creative North Star: The Annotated Archive.** gendertagger should feel like a carefully maintained working archive: quiet parchment underfoot, compact records in stable places, and annotations that reveal the current path without competing with the evidence. The incumbent interface is intentionally plain enough for long review sessions, yet warm enough to remain human.

Human editorial clarity governs every decision. Interfaces are dense because reviewers compare evidence, not because the product is an operations dashboard. Structure comes from type, spacing, hairline borders, and tonal layers; colour names state function; motion confirms state rather than performing. Avoid consumer-dashboard gloss—no decorative gradients, giant KPI theatre, or floating-card scenery.

Key characteristics:

- Warm, theme-aware neutral surfaces keep evidence dominant.
- Annotation violet marks place and selection; registry teal marks action.
- Compact system typography supports sustained bilingual review.
- Borders and tonal shifts carry structure; shadows belong to overlays.
- Canonical vocabulary remains legible in text, not color alone.

## Colors

The light theme places **Quiet Parchment** behind white paper panels and the nearly white raised surface. The dark theme preserves the same hierarchy with warm charcoal rather than absolute black. Text has primary, secondary, and muted roles in both themes; use the weaker roles for supporting information, never to hide required evidence.

**Annotation Marks Place.** Annotation Ink is the violet navigation and selection color. It identifies the current route, selected option, or editorial focus. It is not the default call-to-action color.

**Registry Teal Commits Work.** Registry Teal belongs to primary actions and deliberate state changes. A view should expose one visually dominant action. Do not spread teal across decoration, charts, or passive metadata.

**Vocabulary Is Data.** Male blue, female coral, institution green, and unknown amber are fixed semantic families. Each family has a border, readable text tone, and quiet tint; use all three together. Always print the canonical token or an explicit state alongside color. Certainty tiers reuse these families deliberately: `contested` uses coral, `low` uses amber, and `thin` uses blue.

Verified green, caution gold, and critical red communicate status. Put them beside literal status or error text. Status colors are not suitable as white-text filled badges unless contrast is independently rechecked for the exact theme.

## Typography

The interface uses the native system sans stack. This keeps German and English text familiar, fast, and platform-legible. The mono stack is reserved for controlled-vocabulary tokens, stable identifiers, versions, paths, and hashes.

The scale is intentionally compact: `page` for the single page heading, `title` for cards and panels, `body-strong` for navigation and emphasized rows, `body` for working text, `small` for metadata and controls, and `caption` for the least prominent labels. `display` is exceptional, not a license for marketing-sized headings inside the application shell.

**Compact Does Not Mean Cryptic.** Small text supports comparison only when line height, hierarchy, and plain-language labels remain intact. Do not shrink body copy below the body token to fit more controls.

**One Main Title.** Every view has one `page` heading. Panel titles step down to `title`; labels and metadata step down again. Weight establishes hierarchy before size does, so reserve bold weight for display moments and use semibold for operational emphasis.

## Layout

The desktop shell uses a fixed 15rem sidebar and a flexible content region. Below 1079px the sidebar becomes a 3.75rem icon rail while labels remain available to assistive technology. Pages use their own purposeful maximum width rather than stretching every form, table, or paragraph to the viewport edge.

The review workbench is the signature composition: a 15rem filter column, a flexible list with an 18rem minimum, and an evidence-and-decision column with a 22rem minimum and greater share of available width. It stacks at 68rem. Other incumbent feature layouts adapt around 56rem, 48rem, and 40rem according to their content.

**Four-Pixel Cadence.** Space follows the 4px-based scale. Dense rows use one or two steps internally; cards and panels usually use four; major regions use six to twelve. Prefer `gap` between siblings over compensating margins, and do not introduce off-scale spacing for isolated alignment fixes.

Keep reading and keyboard order aligned with the visual order. At narrow widths, reflow columns rather than creating page-level horizontal scrolling. Preserve a stable evidence context when controls move; compactness must not separate a decision from its provenance.

## Elevation & Depth

**Tonal Layers First.** The page, panel, and raised-surface tones establish hierarchy. Content cards, review rows, inputs, and structural panels stay flat and use hairline borders; they do not cast shadows or lift on hover.

Menus and dialogs are genuinely floating, so they use the single overlay shadow and the theme-appropriate backdrop. No additional elevation ladder exists. A shadow therefore means “temporarily above the document,” not “important.”

State changes use the short state-motion token. Honor reduced-motion preference by reducing transitions to effectively instantaneous. Never add parallax, spring motion, or decorative entrance choreography to evidence and review surfaces.

## Shapes

Controls use the 4px control radius; text fields and popup menus use 8px; cards and review rows use 12px; dialogs use 16px. Badges and compact vocabulary chips use the full pill radius. These levels reflect scope, not personality.

**Shape Follows Scope.** The larger the container and interaction scope, the larger its allowed radius. Do not put pill-shaped buttons beside squared operational controls, and do not round every nested surface independently.

Structural borders are 1px. Keyboard focus is a 2px focus-blue outline with a 2px offset, so it remains distinct from selection borders. Selected review content combines a border with a tonal surface rather than relying on either signal alone.

## Components

**Buttons.** There are exactly three variants: solid for the one primary action, ghost for secondary actions, and text for tertiary or inline actions. Solid buttons use Registry Teal; destructive actions switch border and fill to critical red and require confirmation at the call site. Text buttons underline on hover. Disabled controls reduce opacity and retain an explicit not-allowed cursor.

**Text fields.** Every field has a visible label. Inputs use paper panels, hairline borders, the input radius, and two-by-three-step padding. Field-level errors sit next to the field, use critical text and border color, and connect through `aria-describedby`; do not assign an ambiguous form error to an arbitrary field.

**Compact listboxes.** The trigger uses small type and control geometry. The option popup uses the input radius, one-step internal spacing, the overlay shadow, tonal hover, and Annotation Ink for the selected option. Accessible naming and keyboard behavior come from the headless control, not custom pointer-only behavior.

**Navigation.** Sidebar entries pair a 20px icon with a text label. Hover uses the raised surface; the active route adds Annotation Ink and semibold weight. Disabled destinations are non-links, unfocusable, and visibly subdued. On the icon rail, labels become visually hidden rather than removed.

**Cards and panels.** Project cards and evidence panels use paper-panel backgrounds, hairline borders, card radii, and four-step padding. Card titles use the title role. Links reveal affordance with underlines on hover; the entire card does not float or animate.

**Vocabulary badges.** Badges contain the untranslated canonical token in monospace and may append a plain-language gloss. Their tint, border, and text color move as a tested semantic set. Missing values render an explicit dash with an accessible text alternative, never an empty gap.

**Review rows.** Rows are transparent at rest, tonal on hover, and both tonal and violet-bordered when selected. A semibold name and small identifier sit opposite stacked vocabulary and workflow states. Selection remains explicit through `aria-current` and must survive keyboard navigation.

**Progress and overlays.** Native progress remains a simple full-width track with Registry Teal fill. Dialogs use modal radius, paper panels, the overlay shadow, and a theme backdrop; they trap focus, label their purpose, and return focus when dismissed.

**One Primary Action.** Component variants describe consequence, not visual preference. Adding another solid button to solve hierarchy confusion is a content-structure failure; clarify the workflow instead.

## Do's and Don'ts

### Do

- **Do** keep evidence, provenance, revision, and uncertainty visible where decisions happen.
- **Do** use semantic tokens so light and dark themes preserve the same hierarchy.
- **Do** retain visible labels, keyboard focus, explicit status text, and bilingual expansion space.
- **Do** use monospace selectively for canonical tokens and machine-stable identifiers.
- **Do** place one primary action per view and keep irreversible actions visibly critical.
- **Do** use borders, alignment, and tonal layers before adding elevation.

### Don't

- **Don't** introduce consumer-dashboard gloss: gradients, giant KPI theatre, glass effects, or decorative floating cards.
- **Don't** use raw color values in components or repurpose vocabulary colors for unrelated decoration.
- **Don't** communicate selection, certainty, error, or vocabulary through color alone.
- **Don't** translate canonical label and tier tokens or collapse unknown, abstain, missing, and error states.
- **Don't** use generic confidence bars or imply comparability between method scores without evidence.
- **Don't** add shadows to content cards, hover lift to rows, or animation that competes with review work.
- **Don't** invent data, provenance, or interface states to fill an otherwise quiet surface.
