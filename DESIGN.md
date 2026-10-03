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
    caution-gold-text: "#7a5900"
    caution-gold-tint: "#fdf5e5"
    critical-red: "#d03b3b"
    critical-red-text: "#bf3333"
    critical-red-tint: "#fbeceb"
    information-blue-text: "#1f5aa0"
    information-blue-tint: "#e9f1fa"
    overlay-backdrop: "rgba(11, 11, 11, 0.4)"
    male-violet: "#7056ad"
    male-violet-text: "#60458f"
    male-violet-tint: "#f2edf9"
    female-teal: "#14847d"
    female-teal-text: "#09665f"
    female-teal-tint: "#e7f4f0"
    institution-ochre: "#ae7620"
    institution-ochre-text: "#7d530f"
    institution-ochre-tint: "#faf2e2"
    unknown-gray: "#85817a"
    unknown-gray-text: "#52514e"
    unknown-gray-tint: "#f2f1ee"
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
    night-caution-gold-text: "#e8bd5e"
    night-caution-gold-tint: "#332813"
    night-critical-red: "#f0736f"
    night-critical-red-text: "#f0736f"
    night-critical-red-tint: "#3d201e"
    night-information-blue-text: "#8fbdf0"
    night-information-blue-tint: "#17293d"
    night-overlay-backdrop: "rgba(0, 0, 0, 0.6)"
    night-male-violet: "#a68ad6"
    night-male-violet-text: "#c5b1eb"
    night-male-violet-tint: "#30223f"
    night-female-teal: "#52bcb0"
    night-female-teal-text: "#7bd3c8"
    night-female-teal-tint: "#112f2a"
    night-institution-ochre: "#d6ad58"
    night-institution-ochre-text: "#e5c078"
    night-institution-ochre-tint: "#362b19"
    night-unknown-gray: "#9c9890"
    night-unknown-gray-text: "#c2bfb8"
    night-unknown-gray-tint: "#2c2a27"
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
        backgroundColor: "{colors.female-teal-tint}"
        textColor: "{colors.female-teal-text}"
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

**Registry Teal Commits Work.** Registry Teal belongs to primary actions and deliberate state changes. A view should expose one visually dominant action. Reserve the Registry Teal action token for these controls; vocabulary and charts use their own semantic tokens, including female teal.

**Vocabulary Is Data.** Male violet, female teal, unknown gray, and institution ochre are fixed semantic
families in both themes. Each family has a border, readable text tone, and quiet tint; use all three
together. Always print the canonical token or an explicit state alongside color. Source distribution
bars use the corresponding label solid. Other or multiple source values use a neutral hatch so they
remain distinct from the substantive `unknown` label.

Certainty uses independent status families: `contested` uses critical red, `low` caution gold, and
`thin` information blue. These tones describe evidence support rather than classification. Their
plain-language gloss inherits the readable foreground of its status tint.

Verified green, caution gold, and critical red communicate status. Put them beside literal status or error text. Use `--critical-text` for error and destructive-action text on page, panel, and raised surfaces; reserve `--critical` for fills and borders. Filled destructive buttons keep `--panel` text, verified in both themes. Status colors are not suitable as white-text filled badges unless contrast is independently rechecked for the exact theme.

## Typography

The interface uses the native system sans stack. This keeps German and English text familiar, fast, and platform-legible. The mono stack is reserved for controlled-vocabulary tokens, stable identifiers, versions, paths, and hashes.

The scale is intentionally compact: `page` for the single page heading, `title` for cards and panels, `body-strong` for navigation and emphasized rows, `body` for working text, `small` for metadata and controls, and `caption` for the least prominent labels. `display` is exceptional, not a license for marketing-sized headings inside the application shell.

**Compact Does Not Mean Cryptic.** Small text supports comparison only when line height, hierarchy, and plain-language labels remain intact. Do not shrink body copy below the body token to fit more controls.

**One Main Title.** Every view has one `page` heading. Panel titles step down to `title`; labels and metadata step down again. Weight establishes hierarchy before size does, so reserve bold weight for display moments and use semibold for operational emphasis.

## Layout

Eligible signed-in sessions use the working shell. Signed-out, unresolved, session-error and required-password-change states have a compact header with the home brand, session controls and language/theme choices, with no sidebar or drawer trigger. Legal links remain in the footer.

The desktop working shell uses a 15rem sidebar, or a saved 3.75rem collapsed rail, and a flexible content region. From 720 to 1079 CSS px it uses the rail; below 720px navigation moves to a modal drawer. Labels remain available to assistive technology. Pages use their own purposeful maximum width rather than stretching every form, table, or paragraph to the viewport edge.

The review workbench is the signature composition. Above the queues, provenance and the complete filter form live in native disclosures so they remain available without permanently narrowing the evidence. At 42rem of available content width, the work area uses a queue with an 18rem minimum and one share beside an evidence-and-decision column with a 22rem minimum and two shares; below that it stacks. Within the evidence column, the result summary and source register entry form equal cards at a 32rem detail width and stack below it. The named `app-fact-list` recipe stacks labels above values below a 24rem container width. The `app-page-frame` recipe owns every route edge and the shared page gutter, which is the smaller of four spacing steps and 4vw. Ordinary project workflows use one 60rem maximum page width; report tables scroll locally instead of widening that family. Redigieren and Annotieren alone use the named dense frame modifier for a compact block inset while retaining that horizontal gutter. Workbenches and genuinely wide administrative directories may declare a different named width when their task requires it.

**Four-Pixel Cadence.** Space follows the 4px-based scale. Dense rows use one or two steps internally; cards and panels usually use four; major regions use six to twelve. Prefer `gap` between siblings over compensating margins, and do not introduce off-scale spacing for isolated alignment fixes.

Keep reading and keyboard order aligned with the visual order. At narrow widths, reflow columns rather than creating page-level horizontal scrolling. Preserve a stable evidence context when controls move; compactness must not separate a decision from its provenance.

**Page entry.** The skip link and successful page navigation focus the stable content wrapper. Initial loading, in-page query/hash updates, background refreshes, and open modals preserve their existing focus ownership. Each view owns its H1, task actions, and meaningful content width; route operations stay beside the data or form they affect.

## Elevation & Depth

**Tonal Layers First.** The page, panel, and raised-surface tones establish hierarchy. Content cards, review rows, inputs, and structural panels stay flat and use hairline borders; they do not cast shadows or lift on hover.

Menus and dialogs are genuinely floating, so they use the single overlay shadow and the theme-appropriate backdrop. No additional elevation ladder exists. A shadow therefore means “temporarily above the document,” not “important.”

State changes use the short state-motion token. Honor reduced-motion preference by reducing transitions to effectively instantaneous. Never add parallax, spring motion, or decorative entrance choreography to evidence and review surfaces.

## Optional game-mode character

The optional game mode adds a storybook archive otter in warm brown cut-paper collage, holding a
small silvery-blue paper fish.
It rests beside round setup, follows completed records along the progress track, and presses a stamp
only after an annotation saves. All three poses keep the same bare-eyed appearance; the completed-round
otter holds a library ticket, and paper stars appear once the server saves the round. These moments acknowledge contributions and round
completion, never label correctness or agreement with a method.

Answer choices and saved feedback share a responsive grid row, retaining the four-choice height during
feedback. The inactive choices are invisible and inert; evidence still appears only after saving and can
expand naturally when opened.

This surface alone permits brief decorative sequences up to 800 ms, with no loops, input delay, moving
evidence, or animated focus targets. Reduced motion keeps the otter and stamp static and omits floating
points. The existing panel, text, vocabulary, and control tokens continue to apply. The transparent raster artwork
is decorative and stays the same in both themes; its generation prompt is recorded alongside the
[project asset](frontend/src/assets/game/README.md).

## Shapes

Controls use the 4px control radius; text fields and popup menus use 8px; cards and review rows use 12px; dialogs use 16px. Badges and compact vocabulary chips use the full pill radius. These levels reflect scope, not personality.

**Shape Follows Scope.** The larger the container and interaction scope, the larger its allowed radius. Do not put pill-shaped buttons beside squared operational controls, and do not round every nested surface independently.

Structural borders are 1px. Keyboard focus is a 2px focus-blue outline with a 2px offset, so it remains distinct from selection borders. Selected review content combines a border with a tonal surface rather than relying on either signal alone.

## Components

**Buttons.** There are exactly three variants: solid for the one primary action, ghost for secondary actions, and text for tertiary or inline actions. Solid buttons use Registry Teal; destructive actions switch border and fill to critical red and require confirmation at the call site. Text buttons underline on hover. Disabled controls reduce opacity and retain an explicit not-allowed cursor.

**Control sizing.** Shared buttons, text fields, native single-line fields, and listbox options use a 2rem minimum, rising to 2.75rem below 720 CSS px or with any coarse pointer. Compact styling keeps this minimum. Checkbox/radio geometry and noninteractive badges remain separate; verify label hit areas in each view. Long labels wrap, and fieldsets and fields can shrink within their container.

**Layout recipes.** Shared geometry is opt-in and named in `src/styles/layout.css`. Every page-owning `main` uses `app-page-frame` for containment, gutters, and the ordinary 60rem project-workflow width. Named modifiers cover reading (40rem), authentication (24rem), form (48rem), wide tabular evidence (76rem), and the uncapped dense review/annotation workbenches; feature CSS does not invent another page width. `app-page-heading` and its copy, title, description, and actions elements preserve title-first DOM order and wrap actions after the page identity. `app-form-actions` gives disclosed creation forms one full-width, wrapping action row with the primary commit at the inline end; secondary actions precede it in DOM order. `app-fact-list` provides responsive label/value rows with an overridable label track. `app-card` provides the standard structural boundary for top-level content, task forms, reports, and statistics; `app-resource-card` names that same flat geometry on repeated domain resources. Both use one standard four-step inset, with no feature-local padding variants. The sectioned modifier delegates that inset to full-width child sections. Neither recipe dictates content or action topology. `app-multiline-field` gives native textareas the text-field surface, invalid border, shrinkability, and vertical resize behavior. Feature classes remain available for domain-specific layout; they do not repeat these recipe declarations.

**Scrollable tables.** Use the named `AppScrollRegion` wrapper to contain wide tables. A tab stop and associated visible hint appear only when scrolling is needed. Keep readable columns and semantic table markup; view-specific stacked records remain a separate design choice.

**Inline feedback.** Use `AppFeedback` for concise messages and adjacent recovery actions. Choose static, polite, or assertive announcements explicitly; critical foreground colour is a separate choice. Route-level loading, empty, failure, and recovery regions are structural content and use the shared card boundary. Feedback already inside a card stays inline and does not add a nested card. Keep controls outside the live message. Conflict reconciliation, intentional focus targets, and individual bulk outcomes remain under the view's control.

**Text fields.** Every field has a visible label. Inputs use paper panels, hairline borders, the input radius, and two-by-three-step padding; multiline fields opt into `app-multiline-field` and remain vertically resizable. Field-level errors sit next to the field, use critical text and border color, and connect through `aria-describedby`; do not assign an ambiguous form error to an arbitrary field.

**Compact listboxes.** The trigger uses small type and control geometry. The option popup uses the input radius, one-step internal spacing, the overlay shadow, tonal hover, and Annotation Ink for the selected option. Accessible naming and keyboard behavior come from the headless control, not custom pointer-only behavior.

**Header.** Short breadcrumbs identify the authorized project and current destination. The account name opens Personal settings and Sign out. Project switching sits above project destinations in the sidebar, including its rail and mobile drawer. The current project name labels the switcher button, combining identity and switching without a separate project heading. Names wrap, scientific context and actions stay in their view, and registered unsaved input requires Stay or Discard and leave before path changes or sign-out. See [the global header guidelines](docs/25-frontend-design-guidelines.md#global-header).

**Navigation.** Sidebar entries pair a 20px icon with a text label. Hover uses the raised surface; the active route adds Annotation Ink and semibold weight. Disabled destinations are non-links, unfocusable, and visibly subdued. On the icon rail, labels become visually hidden rather than removed.

**Cards and panels.** Cards are the primary structural language: every major content, task, report, and statistics region uses one paper-panel background, hairline border, card radius, and four-step padding. Page identity, breadcrumbs, and collection headings remain outside. Card titles use the title role. Cards do not nest; inner groups use dividers or closed disclosures so padding does not compound. Links reveal affordance with underlines on hover; the entire card does not float or animate.

**Vocabulary badges.** Badges contain the untranslated canonical token in monospace and may append a plain-language gloss. Their tint, border, and text color move as a tested semantic set. Missing values render an explicit dash with an accessible text alternative, never an empty gap.

**Review rows.** Rows are transparent at rest, tonal on hover, and both tonal and violet-bordered when selected. A semibold name and small identifier sit opposite stacked vocabulary and workflow states. Selection remains explicit through `aria-current` and must survive keyboard navigation.

**Progress and overlays.** Task progress remains a simple full-width track with Registry Teal fill. Source distributions use their label tokens and a neutral hatch for other values. Dialogs use modal radius, paper panels, the overlay shadow, and a theme backdrop; they trap focus, label their purpose, and return focus when dismissed.

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
