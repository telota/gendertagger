# Browser client

The Vue 3 + TypeScript + Vite client for the gendertagger `/api/v1` service. It is an ordinary API consumer
under [ADR-0006](../docs/decisions/ADR-0006-vue-browser-client-boundary.md): it holds no scientific logic,
never talks to Celery, Redis, or the database, and depends on no filesystem detail.

The milestone plan is [`docs/24-frontend-delivery-plan.md`](../docs/24-frontend-delivery-plan.md). Milestone M1
(scaffold and transport) is in place; the application shell (M2) and every screen after it are not.
`gendertagger.html` is the accepted wireframe. It is a layout and information-architecture reference only, and
its interaction markup must not be carried over.

Read before changing anything here:

- [`docs/26-frontend-coding-guidelines.md`](../docs/26-frontend-coding-guidelines.md)
- [`docs/25-frontend-design-guidelines.md`](../docs/25-frontend-design-guidelines.md)
- [`docs/17-frontend-integration.md`](../docs/17-frontend-integration.md)
- [`docs/05-api.md`](../docs/05-api.md)

## Requirements

Node `^26.9.0` (declared in `package.json` `engines`, enforced by `.npmrc`, and pinned to the same version in
[`deploy/docker/frontend.Dockerfile`](../deploy/docker/frontend.Dockerfile) and `.gitlab-ci.yml`). Install from
the committed lockfile:

```bash
npm --prefix frontend ci
```

## Commands

Run from the repository root with `npm --prefix frontend run <script>`, or from `frontend/`.

| Script | Purpose |
|---|---|
| `dev` | Vite development server; proxies `/api/v1` to `http://localhost:8000` so requests stay same-origin |
| `build` | Production build into `dist/` |
| `lint` | ESLint with the Vue, TypeScript, accessibility, and i18n rules; warnings fail |
| `format:check` | Prettier |
| `typecheck` | `vue-tsc` over the application, the tests, and the tool configuration |
| `test` | Vitest with an 80 % branch-coverage floor |
| `api:generate` | Regenerate `src/api/schema.d.ts` from the OpenAPI contract |
| `api:check` | Fail when `src/api/schema.d.ts` is stale |
| `i18n:check` | Fail on message-catalogue drift between locales |
| `check` | `typecheck`, `i18n:check`, `api:check`, and `test` in one run; the pre-push hook |

## Transport contract

`src/api/schema.d.ts` is generated, never edited. Its source is the committed OpenAPI snapshot
[`contracts/openapi-v1.json`](../contracts/openapi-v1.json). The backend contract test already fails
when the live FastAPI schema differs from that snapshot, so a contract change follows one path:

1. update the snapshot in the backend change with `uv run --locked python scripts/update_openapi_snapshot.py`,
   run from `backend/`;
2. run `npm --prefix frontend run api:generate` from the repository root;
3. commit the regenerated `schema.d.ts` with it.

`api:check` runs in CI and fails when step 2 was skipped. `src/api/` is the only place that issues HTTP: the
typed client sends the session cookie, attaches the CSRF header to every unsafe method, and `unwrap` turns a
failure into an `ApiError` classified by the shared envelope's stable `code`.

The CSRF cookie and header names in `src/api/csrf.ts` (`csrf_token`, `X-CSRF-Token`) match the local account
provider from [ADR-0031](../docs/decisions/ADR-0031-local-database-authentication.md), which sets the cookie at
`POST /api/v1/auth/login`. Both names must change together with `gendertagger.api.authentication`.

## Layout

```text
src/
  api/          generated types, typed client, error and CSRF handling
  app/          composition root, router, i18n, sidebar, header, footer, query client
  components/   base primitives (button, text field, listbox) and domain components (still empty)
  composables/  reusable stateful logic: the injected API client, GET /api/v1/branding, theme, locale
  features/     one directory per screen: home, legal notice, login, change password, projects, not found
  locales/      message catalogues, one JSON file per locale
  stores/       Pinia stores for shared client state: the session and its roles
  styles/       design tokens and global styles
  types/        local types that are not transport types
tests/          unit, component, and policy tests
public/         theme-init.js, resolved before first paint
nginx/          history-mode fallback for the production image
```

The shell is a fixed sidebar (`AppSidebar`: brand, the one navigation surface per decision D7) plus a
content region (`AppHeader`: locale/theme switches and session state; the routed view; `AppFooter`), per
[`docs/25-frontend-design-guidelines.md`](../docs/25-frontend-design-guidelines.md).

Design tokens in `src/styles/tokens.css` are semantic and theme-scoped. `tests/styles/tokens.spec.ts` checks
that both themes stay complete and that each pairing published in the design guidelines still measures what
the document claims.

## Dependencies

Every direct dependency is pinned to an exact version and justified here, because the frontend image publishes
an SBOM. Versions were chosen for mutual compatibility, not recency: TypeScript stays on 5.9 because
`openapi-typescript` requires 5.x and `typescript-eslint` requires a version below 6.1.

| Package | Licence | Why the platform is not enough |
|---|---|---|
| `vue` | MIT | The framework fixed by ADR-0006 |
| `vue-router` | MIT | History-mode routing (decision D13), needed by the public legal notice route and, from M2, project navigation |
| `vue-i18n` | MIT | Locale-aware plural, date, and number formatting (ADR-0030) |
| `pinia` | MIT | The session and its roles — genuinely shared client state, per docs/26-frontend-coding-guidelines.md |
| `@headlessui/vue` | MIT | The one behavioural dependency decision D9 admits, for Menu, Dialog, and Listbox; brings its own `@tanstack/vue-virtual` (MIT). Covers three of the four named primitives — it ships no Tooltip, which is hand-rolled in-house per D9's resolution in [`24-frontend-delivery-plan.md`](../docs/24-frontend-delivery-plan.md) |
| `@tanstack/vue-query` | MIT | Server-state cache for cursor-paginated collections (docs/23-wireframe-ui-inventory.md), starting with the project list; brings `@tanstack/query-core` and `vue-demi` (both MIT) |
| `openapi-fetch` | MIT | A small typed `fetch` wrapper over the generated schema |
| `vite`, `@vitejs/plugin-vue`, `vue-tsc`, `typescript` | MIT / Apache-2.0 | Build and type checking |
| `vitest`, `@vitest/coverage-v8`, `@vue/test-utils`, `jsdom` | MIT | Test runner, component mounting, coverage floor |
| `axe-core` | MPL-2.0 | Automated accessibility checks in component tests; test-only, never bundled |
| `eslint` and its Vue, accessibility, and i18n plugins | MIT | Enforce the coding guidelines |
| `openapi-typescript` | MIT | Generates the transport types |
| `prettier` | MIT | Formatting |

`axe-core` is the only dependency under a weak copyleft licence. It runs only in tests and is not part of the
shipped bundle, but review it if the licence policy is strict.

`useBranding()` still fetches independently per component rather than through the shared cache above — it
predates it, is small and unauthenticated, and moving it over is not yet worth the churn.

## Session and login

`src/stores/session.ts` (`useSessionStore`) resolves the session once at app start against `GET /api/v1/me`
and `GET /api/v1/auth/session`, and backs `/login`, `/change-password`, and the header's signed-in state
(ADR-0031, ADR-0032). `useApiClient()` is called at the top of the store's `setup()` so Pinia's
inject()-in-setup-stores support resolves it correctly; do not call it lazily inside an action.

A view that must not render while signed out (so far, `/change-password` and `/projects`) has to wait for
the store's one `loading` -> `ready` transition before deciding, rather than reading `isSignedIn`
immediately on mount — `session.initialize()` is still pending at that point on every fresh page load,
cookie or not. `session.status` also distinguishes an ordinary `401` (not signed in) from any other
failure — a `5xx`, a network error — as its own `error` status, so a genuine server problem at boot renders
as one rather than as a misleading "please sign in".

## Projects (M3)

`/projects` (`ProjectListView.vue`) is the first screen built on `GET /projects` and the shell's first use
of the shared query cache, through `useProjects.ts`. Project creation (`POST /projects`) is offered to
global operators and admins only (decision D6); every other role sees the list without it.

`/projects/:projectId/overview` (`ProjectOverviewView.vue`) shows a project's own facts (name, slug, role,
description) and links to import. It deliberately does not attempt the wireframe's KPI dashboard yet — that
reads `GET /aggregations/{id}/review-summary`, which needs a run and an aggregation neither of which can
exist before M4.

`/projects/:projectId/import` (`ImportView.vue`, `useSnapshotImport.ts`) uploads one file to
`POST /projects/{project_id}/snapshots` and polls `GET /snapshots/{snapshot_id}` via the new
`composables/usePolledQuery.ts` — the generic `202` → poll → terminal-state composable
docs/23-wireframe-ui-inventory.md calls for, built now since it already names four consumers (snapshots,
aggregations, evaluations, exports). Import is a project-scoped operator action (checked against
`current_user_role`, not the global roles D6 gives project creation). The form covers the whole
`source_format` × `packaging` matrix the backend accepts (TEI as single, loose, zip, or tar.gz; CSV, XLSX,
and JSON as single only) and shows `GET /snapshot-upload-limits` before upload. It also refuses an archive file chosen under a
non-archive delivery (or the reverse) before uploading. The wireframe's GitLab source is a v1 scope exclusion.

Test-environment note: constructing a `File` for a `FormData` body in a test must use `node:buffer`'s
`File`, not jsdom's — Vitest's Node-`fetch` compatibility layer can't read a jsdom `File` inside a
`FormData`, a jsdom/Vitest/undici interop gap that does not exist in a real browser. See
`tests/features/projects/import.spec.ts`'s `testFile()` helper.

Other nested `/projects/:projectId/...` routes from
[`docs/23-wireframe-ui-inventory.md`](../docs/23-wireframe-ui-inventory.md) are added as their own screens
land, not stubbed ahead of them.

## Branding

The footer, the start page, and `/impressum` render `GET /api/v1/branding` ([ADR-0036](../docs/decisions/ADR-0036-institution-branding-configuration.md))
through `src/composables/useBranding.ts`, never a hard-coded fact. The one exception is the software's own
source-code licence in `src/app/publication.ts`, which is the same for every deployment. See
[`docs/25-frontend-design-guidelines.md`](../docs/25-frontend-design-guidelines.md#publication-details-footer-and-legal-notice)
for the guideline mapping and this deployment's configured values.
