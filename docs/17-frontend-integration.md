# Frontend integration and browser-client contract

## Decision

The browser UI uses Vue 3, TypeScript, and Vite. It is an ordinary client of the public FastAPI API, not a
privileged application layer or second source of truth. The backend remains usable without it by CLI, tests,
external integrations, and future clients.

## Boundary

```text
Vue browser client
      |
      | HTTPS / JSON / SSE
      v
FastAPI /api/v1
      |
      v
Application services
```

The browser never depends on SQLAlchemy models, database tables, Celery task IDs, worker identities, Redis
keys, queue names, filesystem paths, Python implementation details, or classifier-internal APIs.

Scientific normalization, aggregation, permission checks, and final-decision resolution remain on the
backend. UI-specific view models may present server resources but must not redefine their semantics.

## Transport generation

FastAPI OpenAPI is the machine-readable transport contract. The committed snapshot generates
`frontend/src/api/schema.d.ts`; that file is never edited by hand. CI regenerates it and fails on drift.

The runtime client is a small handwritten `openapi-fetch` wrapper parameterized by the generated `paths`
type. It centralizes same-origin requests, credentials, CSRF attachment, and error-envelope parsing. UI code
must not create parallel transport types or issue ad hoc requests outside `frontend/src/api/`.

Exact generation commands and review steps live in [`CONTRIBUTING.md`](../CONTRIBUTING.md). Frontend-specific
commands and dependency rationale live in [`frontend/README.md`](../frontend/README.md).

## API consumption rules

Backend resource, lifecycle, pagination, review-query, event, error, and concurrency semantics are defined in
[`05-api.md`](05-api.md). Exact paths, parameters, payloads, responses, and status codes come from OpenAPI.
The browser follows these integration rules:

- long-running commands retain the returned resource ID and observe persisted state rather than Celery;
- SSE is an optional live view, and disconnect recovery always refetches the resource;
- server resources remain server state; large collections are not downloaded for browser-side filtering or
  scientific ordering;
- cursors remain attached to the complete query that produced them;
- list summaries render collections without one detail request per row;
- a stale annotation write reloads current history/revision and asks the reviewer to decide again;
- unsent scholarly decisions survive authentication recovery and transient transport failures.

Review-specific behavior is defined in
[`09-annotation-and-review.md`](09-annotation-and-review.md). The client never silently overwrites a conflict
or treats an optimistic local state as a completed scholarly write.

## Browser authentication

The browser uses the local account provider's secure HTTP-only session cookie. The transport reads the
separate CSRF cookie and mirrors it into the configured header for every unsafe request. Long-lived bearer
tokens are never stored in JavaScript-accessible storage.

The shell handles login, logout, forced password change, and session restoration through the generated
contract. A `401` during ordinary work opens inline authentication without discarding unsent input; login's
own `401 invalid_credentials` remains a form error. Project controls follow the effective project role
returned by the API, but backend authorization remains authoritative.

The complete provider, session-lifetime, CSRF, password, and role semantics live in
[`13-auth-and-security.md`](13-auth-and-security.md),
[ADR-0031](decisions/ADR-0031-local-database-authentication.md),
[ADR-0032](decisions/ADR-0032-sliding-session-lifetime.md), and
[ADR-0033](decisions/ADR-0033-project-scoped-membership-roles.md).

## Same-origin deployment

Production serves the Vue assets and `/api/v1` through one origin. The reverse proxy owns TLS and routing;
same-origin requests simplify secure cookie authentication and avoid general production CORS.

Vite development proxies `/api/v1` to FastAPI so application requests remain same-origin from the browser's
perspective. If an explicit development origin is enabled instead, wildcard CORS is forbidden with
credentials.

## State ownership

Generated OpenAPI types and the typed client own transport shapes. A server-state query/cache layer owns
resource fetching, invalidation, polling, and query-scoped cursors. Pinia is reserved for genuinely shared
client state such as session presentation, current route context, and effective presentation—not copies
of backend resources. Under [ADR-0043](decisions/ADR-0043-account-level-user-preferences.md), saved account
preferences are server state: fetch and cache them by principal, clear private state on logout/account
changes, and use canonical PATCH responses with their revision. The lazy `/settings` route, named
`userSettings`, is available to every resolved, password-current account regardless of project or global
role. Its translated link belongs to the title-bar account controls. The form keeps its editable draft in
component state; changing a control or restoring defaults does not save or change the shell. Explicit Save
sends `expected_revision`, and only the canonical successful response replaces saved query state.

A saved locale of null means browser default: the browser resolves its effective language without writing
that result back: first supported browser-language primary subtag, then German. Theme `system` similarly
follows the browser. The saved desktop-collapse choice applies at widths of at least 1080 CSS pixels;
responsive layout and temporary mobile navigation never save `desktop_sidebar_collapsed`.

Read errors offer retry, and save errors retain the draft without presenting a successful save. A
`409 preferences_revision_conflict` retains the draft and requires a deliberate reload of saved values
before another save; never silently replay it with a fresh revision. A principal change invalidates
private preferences and outstanding request ownership, so a late result cannot alter another account's
cache, draft, or effective presentation.

The existing `gendertagger.locale` and `gendertagger.theme` localStorage keys belong only to anonymous
browser presentation. Preserve existing values as anonymous choices without migrating them into accounts.
Before identity resolution, startup rendering may use these choices; after resolving an authenticated
account, its API preferences are authoritative. While its initial preferences read is pending or fails,
use the account defaults (browser-default locale, system theme, expanded desktop sidebar), never another
account's or the anonymous browser's choices. Do not maintain an account preferences startup cache in
localStorage. Logout restores the unchanged anonymous language/theme choices. These effective fallback
values are presentation only and must never masquerade as a successful API read or save.

Optimistic presentation is permitted only when failure remains visible and cannot obscure an unsuccessful
annotation or other scholarly write.

## Upload and download boundary

The browser uploads source material and downloads generated artifacts through API resources. It never sends
or receives server filesystem paths. Upload limits are surfaced before transfer and from structured `413`
errors. Downloads remain authorized resource operations.

Signed-URL delivery for very large artifacts is deferred in
[`22-future-development.md`](22-future-development.md).
