# Frontend coding guidelines

## Purpose and authority

These rules govern the Vue 3 + TypeScript client. They extend, and never override,
[`18-engineering-and-quality.md`](18-engineering-and-quality.md) for toolchain and CI policy and
[`19-coding-and-documentation-style.md`](19-coding-and-documentation-style.md) for documentation, English
usage, and contract vocabulary. The client boundary itself is fixed by
[`17-frontend-integration.md`](17-frontend-integration.md) and
[ADR-0006](decisions/ADR-0006-vue-browser-client-boundary.md).

Visual and interaction rules are in [`25-frontend-design-guidelines.md`](25-frontend-design-guidelines.md).

The governing constraint, from rule 16 of [`AGENTS.md`](../AGENTS.md): the client is an ordinary `/api/v1`
consumer. It does not duplicate scientific logic, does not create page-specific business rules, and does not
depend on ORM, Celery, Redis, or filesystem details.

## Toolchain and dependencies

- Node 26, pinned. The version is declared in `frontend/package.json` `engines` and in the Dockerfile, and
  the two must agree.
- `frontend/package.json` and `frontend/package-lock.json` own the client's dependencies. The repository
  root `package.json` remains the Pyright-only development tool manifest and does not gain client
  dependencies. The build context for
  [`deploy/docker/frontend.Dockerfile`](../deploy/docker/frontend.Dockerfile) is `frontend/`.
- CI installs with `npm ci` from the committed lockfile. Never `npm install` in CI.
- Direct dependencies and development tools are pinned to exact versions, matching the Python policy in
  [`18-engineering-and-quality.md`](18-engineering-and-quality.md).
- Every new dependency is justified in the merge request: what it does, why the platform is insufficient,
  its licence, and its transitive weight. The frontend image publishes an SBOM, so dependencies are
  governance surface, not a free choice.
- Decision D9 admits exactly one behavioural dependency beyond the framework: a small headless
  accessibility library for overlay primitives (menu, modal, listbox, tooltip). It supplies behaviour and
  focus management only; its visual defaults are not used. Charting libraries are excluded by decision
  D10 — charts are hand-rolled SVG against the tokens.

## Project structure

```text
frontend/
  src/
    api/            generated schema types + typed client; nothing else
    app/            application entry, router, i18n, plugin registration
    assets/         static assets
    components/     reusable presentational components
      base/         primitives (button, chip, pill, table, modal, ...)
      domain/       domain components (label badge, tier indicator, ...)
    composables/    reusable stateful logic
    features/       one directory per screen; views + screen-local components
    locales/        message catalogues
    stores/         Pinia stores for genuinely shared client state
    styles/         tokens, resets, global styles
    types/          shared local types that are not transport types
  tests/
```

Cross-feature imports are forbidden: a `features/review` module must not import from `features/import`.
Anything shared moves to `components/`, `composables/`, or `types/`.

## Naming

| Construct | Form | Example |
|---|---|---|
| component file and name | `PascalCase` | `ReviewItemRow.vue` |
| composable file and function | `camelCase` with `use` prefix | `useCursorPage.ts`, `useCursorPage()` |
| store file and function | `camelCase` with `use` prefix and `Store` suffix | `useSessionStore` |
| other module | `camelCase` | `formatTeiId.ts` |
| type, interface, enum | `PascalCase` | `ReviewFilterState` |
| constant | `UPPER_SNAKE_CASE` | `DEFAULT_PAGE_SIZE` |
| CSS custom property | `--kebab-case` | `--text-secondary` |
| i18n key | dot-separated `camelCase` segments | `review.actions.defer` |
| test file | mirrors subject | `ReviewItemRow.spec.ts` |

Domain terms follow [`19-coding-and-documentation-style.md`](19-coding-and-documentation-style.md) exactly.
A frontend variable holding a certainty tier is `certaintyTier`, never `confidence`. `unknown`, `abstain`,
and `error` stay distinct in code as they do in the contract. Acronyms are words: `apiClient`, `teiId`.

Component names are multi-word, so no component collides with a current or future HTML element. Booleans
read as predicates: `isStale`, `hasConflict`, `canAnnotate`.

## TypeScript

- `strict` is on, including `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes`.
- `any` is forbidden. Use `unknown` and narrow. A cast requires a comment stating why the compiler cannot
  see what you know.
- Non-null assertion (`!`) is forbidden outside tests. Handle the absent case.
- `as const` for literal unions; prefer union types over TypeScript `enum`.
- Use `import type` for type-only imports so the bundler can drop them.
- Model asynchronous resources as discriminated unions rather than parallel booleans:

```ts
type Async<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: T; isStale: boolean }
  | { status: 'error'; error: ApiError }
```

- Exhaustive `switch` over canonical labels, tiers, and statuses, with a `never` default. When the backend
  adds a tier, the build must fail rather than the UI silently rendering nothing.

## Transport layer

- Transport types are **generated** from the FastAPI OpenAPI document, taken from the committed snapshot
  `contracts/openapi-v1.json` that the backend contract test already guards. Hand-writing or
  hand-editing a type that mirrors a Pydantic model is forbidden; CI regenerates and fails on drift.
- `src/api/` is the only place that knows about HTTP. No component, composable, store, or view issues a
  request directly.
- Requests are same-origin with `credentials: 'include'`. The CSRF token is attached centrally to every
  unsafe method; no call site opts out.
- Never construct an endpoint path by string concatenation at a call site; go through the typed client.
- Server-derived values are never recomputed locally. Do not re-derive a certainty tier, an agreement share,
  a final decision, or a normalised label in TypeScript. If the client appears to need one, the endpoint is
  wrong — raise it rather than working around it.
- Query parameters for a cursor page are carried as one object, and the cursor is stored together with the
  exact filter and sort tuple that produced it. A cursor is never reused across a changed query.

## Vue single-file components

- `<script setup lang="ts">` only. Options API and mixins are not used.
- Block order: `<script setup>`, `<template>`, `<style scoped>`.
- Props and emits are declared with type-only generics and validated at the boundary:

```ts
const props = defineProps<{ item: ReviewItem; isSelected: boolean }>()
const emit = defineEmits<{ select: [id: string]; annotate: [action: ReviewAction] }>()
```

- Props are read-only. Never mutate a prop or an object reached through one; emit instead.
- Emitted event names are verbs in the past or imperative form, and are documented by their payload type.
- One component, one responsibility. A component that both fetches and renders a complex screen is split
  into a container view under `features/` and presentational components.
- `v-for` requires a stable domain key — `tei_id` or a resource `id`. Array index keys are forbidden.
- `v-if` and `v-for` never appear on the same element.
- Template expressions stay trivial. Anything with a condition or a computation moves to a `computed`.
- Components render what they are given; a presentational component does not call the API.

## Composables

- Named `useX`, returning a plain object of refs, computeds, and functions.
- No side effects at module scope. Everything that starts a subscription, an interval, or a listener also
  cleans it up in `onScopeDispose` or `onUnmounted`.
- Composables are called synchronously at setup top level, never inside conditionals or loops.
- Shared logic that is not stateful belongs in a plain function, not a composable.

The following are built once and reused everywhere, per
[`23-wireframe-ui-inventory.md`](23-wireframe-ui-inventory.md): error envelope handling, `409` conflict
recovery, `413` upload limits, the `202`-poll lifecycle, SSE with reconnect, cursor pagination, role checks,
and CSRF attachment.

## State ownership

- **Server state** lives in the query/cache layer, keyed by resource and query. It is never copied into a
  store "so components can reach it".
- **Pinia** holds only genuinely shared client state: the session and roles, the active
  project/snapshot/run/aggregation selection, effective locale/theme, and transient collapsed sections.
  Saved account preferences from `/me/preferences` are principal-scoped server state, governed by
  [ADR-0043](decisions/ADR-0043-account-level-user-preferences.md). Do not mirror their canonical resource
  into an independent browser settings store or persist breakpoint-derived layout as desktop preference.
- **Personal preference drafts** remain local to `/settings`. Save sends the last canonical revision and
  installs the canonical response only for the initiating principal. Retain drafts after failures;
  `409 preferences_revision_conflict` blocks replay until an explicit saved-value reload. Invalidate
  pending read and write ownership on logout or an account change as well as clearing private query state.
  Sidebar controls send only their changed field and revision; they never submit another view's draft.
  Independent controls may race and must retain the same explicit conflict recovery. The mobile drawer's
  open state stays local to the shell and never writes the saved desktop preference.
- **Anonymous presentation storage** owns the existing `gendertagger.locale` and `gendertagger.theme`
  keys. Never migrate them into an account or write account choices back to them. There is no account
  startup cache; the precedence and pending/error defaults are defined in
  [`17-frontend-integration.md`](17-frontend-integration.md#state-ownership).
- **Component state** holds everything local: open/closed, hovered, draft input.
- Route parameters are the source of truth for resource context. A store never holds an identifier that the
  URL should carry — a review queue must be shareable by link.
- Optimistic updates are permitted only where a failed write cannot be mistaken for a successful scholarly
  decision. Annotations are not optimistic: the server assigns the resulting revision.

## Routing

- `vue-router` in history mode, with the SPA fallback added to the frontend nginx image.
- The route shape follows [`23-wireframe-ui-inventory.md`](23-wireframe-ui-inventory.md) and carries the
  aggregation identifier explicitly.
- Guards handle authentication and role requirements; they never duplicate authorization, which the server
  owns. A guard failing closed on the client is a convenience, not a control.
- The lazy `userSettings` route at `/settings` requires a resolved, signed-in, password-current session
  without a project or global role requirement. Keep its account-control link separate from administrative
  branding settings.
- Filter and sort state that a reviewer would want to share or revisit lives in the query string.

## Error handling

- Every failure path is handled. Empty `catch` blocks and bare `.catch(() => {})` are forbidden.
- The shared `ApiErrorEnvelope` is parsed centrally; user-facing text is selected from the stable `code`,
  never by matching on message strings.
- `409` with `annotation_conflict` triggers the designed reconciliation flow, not a generic error.
- `413` maps onto the import limits presentation.
- `401` first offers an inline sign-in prompt and retries the request in place (decision D1;
  `src/app/sessionGuard.ts`); only once that is declined does it clear the session and route to login,
  preserving the intended destination.
- Never surface a raw exception, stack trace, or backend internal to the user. The request ID may be shown
  for support purposes.
- Do not log person data, source content, or raw method output to the browser console, mirroring the backend
  logging rule in [`18-engineering-and-quality.md`](18-engineering-and-quality.md).

## Internationalisation in code

- No user-facing string literal in a component. A lint rule enforces this.
- Keys are structured by feature: `review.filters.certaintyTier.contested`.
- Never build a sentence by concatenating translated fragments; use interpolation with named placeholders so
  translators control word order.
- Use the i18n library's plural and date/number formatting; never hand-roll them.
- Canonical labels, tier names, prediction statuses, and identifiers are rendered from their token and are
  excluded from translation. A gloss, where used, is a separate key.
- A missing-translation check runs in CI and fails the build.

## Styling

- Scoped styles in components. No global styles outside `src/styles/`.
- Colours, spacing, radii, and type steps come from tokens. A raw hex value, a raw pixel spacing, or a
  hard-coded font size in a component is a review rejection.
- Tokens are semantic and theme-scoped (decision D8). A component references `--text-secondary`, never a
  theme-specific name and never a literal. No component branches on the active theme, and no style is
  written for one theme only; if a rule needs a theme condition, the token layer is wrong.
- Never derive the dark theme with `filter: invert()` or a translucent overlay.
- No deep selectors into a child component's internals (`:deep()` requires a comment justifying it).
- No `!important`.
- Utility classes, if introduced, are token-backed and enumerable; ad-hoc inline `style` attributes carrying
  layout are not used. Inline style is acceptable only for genuinely dynamic values such as a computed bar
  width.
- The label palette is applied only through the domain components that own it. A component does not reach
  for `--male` directly.

## Accessibility in code

Target is WCAG 2.2 AA. Automated checks are a floor, not a strategy: none of the wireframe's non-semantic
toggles, sliders, or checkboxes would have been fully caught by them.

- Interactive elements are `<button>` or `<a href>`. `role="button"` on a `div` is forbidden.
- Every form control has an associated `<label>`; icon-only controls carry an accessible name.
- Focus is visible, never removed. Modals trap focus and restore it on close.
- Dynamic status changes are announced through a live region.
- Images and icons that carry meaning have text alternatives; decorative ones are hidden from assistive
  technology.
- Keyboard shortcuts are suppressed while a text input has focus.
- Native form controls before ARIA. A switch is `<input type="checkbox" role="switch">` or a real button with
  `aria-checked`, never a styled `<span>`. Reach for a custom widget pattern only when no native element
  fits, and then take it from the D9 library.
- Decorative icons and glyphs carry `aria-hidden="true"`; meaningful ones carry an accessible name. A bare
  Unicode symbol is never left in the accessibility tree.
- Canonical labels and tier names render in English inside a German interface (decision D3), so they carry
  `lang="en"` where they appear as prose, giving screen readers the right pronunciation.
- Font sizes and text-tracking spacing use `rem`, never `px`, so browser font settings apply.
- Live regions are created once and updated, never inserted on demand, and are not used for content the user
  can already see change.
- `axe-core` runs in component tests and fails CI on violations; the linter's Vue accessibility ruleset runs
  in `lint`. Neither replaces the manual passes required by decision D17 — keyboard on every screen in both
  themes and locales, NVDA with Firefox, VoiceOver with Safari, and a zoom/reflow check at 400 % — which are
  recorded with date, scope, and findings. The assessment is internal (D16), so that record is the only
  evidence there is.

## Testing

Layers, mirroring the backend pyramid in [`14-testing.md`](14-testing.md):

| Layer | Covers |
|---|---|
| unit | pure functions, formatters, composable logic |
| component | rendering, props/emits contracts, states, accessibility roles |
| integration | screens against a mocked transport layer, including error and conflict paths |
| end-to-end | the review path against a seeded snapshot in a running stack |
| accessibility | automated `axe-core` per component, plus the recorded manual passes of the D17 matrix |

Rules:

- Tests describe behaviour, not implementation. Query by role and accessible name; do not select by CSS
  class or component internals.
- Network is mocked at the transport boundary, not by stubbing component methods.
- Every interface state from [`25-frontend-design-guidelines.md`](25-frontend-design-guidelines.md) that a
  component declares has a test.
- The `409 annotation_conflict` path and the `202`-poll lifecycle have explicit tests; they are the two
  flows most likely to be silently wrong.
- At least one end-to-end path per locale.
- The M5 exit criterion — a reviewer corrects a machine result and the final-decision view changes without
  mutating `Prediction` or `AggregatedResult` — is an end-to-end test, not a manual check.
- Branch coverage with an **80 % floor** (decision D11), enforced in the `coverage` stage from the first
  milestone. The floor is ratcheted upward as the suite matures and is never met by writing tests against
  implementation details. Tests are written alongside the code, not scheduled afterwards.
- Component tests run in both themes and both locales where rendering differs; the theme and locale
  switches are themselves tested.

## Performance

- Server-side filtering, sorting, and cursor pagination always. Never fetch a whole collection to filter it
  in the browser.
- Route-level code splitting; the game mode and statistics screens are lazy.
- Long lists are virtualised only when a real page size makes it necessary; correctness and accessibility
  come first.
- Debounce free-text search before it reaches the server, and cancel superseded requests.
- SSE connections are opened once per run view and closed on unmount. On reconnect, refetch current state
  rather than assuming continuity — no event log is replayed.

## Security

- No token in `localStorage` or any JavaScript-reachable storage. Authentication is the HTTP-only session
  cookie; CSRF protection is mandatory on unsafe methods.
- `v-html` is forbidden. TEI snippets and any source-derived content render as text. Source material is
  untrusted input.
- No third-party script, font, analytics, or asset loaded from another origin. The deployment is
  same-origin by design.
- Do not put identifiers or person data in URLs sent anywhere other than the API, and do not include them in
  client-side telemetry.
- Uploaded files are passed to the API unmodified; the client does not parse, rewrite, or preview source
  material it has not been given by the server.

## Prohibited patterns

- Duplicating a Pydantic contract as a hand-written TypeScript type.
- Recomputing a label, tier, agreement share, or final decision in the client.
- A confidence threshold or percentage anywhere in the interface (decision D2).
- Translating canonical labels or tier names (decision D3).
- Reaching for Celery IDs, queue names, database fields, or filesystem paths.
- `any`, non-null assertions outside tests, empty catch blocks, `v-html`, `!important`, index keys.
- Global event buses, cross-feature imports, and page-specific backend endpoints.
- Theme-conditional styling in components, and hard-coded palette values of either theme.
- Non-semantic interactive elements, unlabelled controls, `px` font sizes, and unhidden decorative glyphs.
- A charting library, or an overlay primitive hand-rolled instead of taken from the D9 library.

## Automated validation

Established during M1 and required for merge:

```bash
npm --prefix frontend ci
npm --prefix frontend run lint          # ESLint: vue, typescript, a11y, i18n rules
npm --prefix frontend run format:check  # Prettier
npm --prefix frontend run typecheck     # vue-tsc --noEmit
npm --prefix frontend run test           # vitest, 80% branch-coverage floor
npm --prefix frontend run build
npm --prefix frontend run api:check     # regenerate transport types, fail on drift
npm --prefix frontend run i18n:check    # fail on missing or orphaned message keys
```

These join the existing `validate` and `test` stages in `.gitlab-ci.yml` alongside the Python gates, and run
in pre-commit where fast enough. As with the backend, CI is the final arbiter and local hooks are a
feedback mechanism.
