# Authentication and authorization

Authentication is required because the system supports imports, compute jobs, and scholarly annotations.

## Role model

Authorization is scoped to projects ([ADR-0033](decisions/ADR-0033-project-scoped-membership-roles.md)).
[`models/user.py`](../src/gendertagger/models/user.py) defines two hierarchical role vocabularies.

`ProjectRole` is held per project, through a membership in `project_memberships`, one role per user and
project:

- `viewer`: read the project and everything it owns
- `reviewer`: viewer + create annotations
- `operator`: reviewer + import snapshots, create runs/aggregations/evaluations/exports

`GlobalRole` applies outside any one project:

- `operator`: create projects; the creator becomes the new project's `operator`. It grants no access to
  any other project.
- `admin`: `operator` capability in every project, plus project-membership administration

A caller's effective role in a project is `operator` for a global `admin`, otherwise its membership role,
otherwise none.

[`api/authorization.py`](../src/gendertagger/api/authorization.py) enforces this in application
dependencies rather than only hiding controls in the frontend. Each project-scoped route asks a
`ProjectAccessGuard` for the caller's role in the project that owns the route's root identifier; every
snapshot, run, aggregation, evaluation, and export has exactly one owning project. A resource that does not
exist and a resource in a project where the caller has no role both return `404 resource_not_found`, so an
identifier from another project reveals nothing. A member whose role is below the route's least role
receives `403 forbidden`. `require_project_creator` and `require_admin` gate project creation and membership
administration, and `require_any_grant` admits any caller holding a global role or a membership to the
routes that read no project data. [`05-api.md`](05-api.md) lists the root identifier and least role of every
route.

Administrators manage memberships through the admin-only `/api/v1/projects/{project_id}/members` endpoints
or the `gendertagger projects add-member`, `remove-member`, and `list-members` CLI commands.

## Data safety

- bound each upload part and the complete multipart collection before acceptance
- parse XML with secure settings; no external entity resolution, network, DTD loading, or recovery
- normalize source-member names and reject absolute paths, traversal, controls, and normalized collisions
- read ZIP and TAR.GZ members without filesystem extraction; reject links, devices, sparse files, encryption,
  nested containers, unsupported members, and expansion-limit violations
- preflight classic ZIP and ZIP64 central-directory counts and derived metadata size before constructing member
  objects
- inspect XLSX as an untrusted ZIP container using bounded secure OOXML parsing before a read-only streaming
  workbook load; reject macro/dialog/VBA parts or content types, decoded external relationships, formulas,
  hyperlinks, merged cells, excessive dimensions, ambiguous populated worksheets, non-string values, and
  expansion-limit violations
- apply persisted member-count, expanded-byte, compression-ratio, record-count, and tabular-cell limits
- reject oversized JSON integer tokens and JSON/CSV U+0000 strings as permanent source errors
- reject duplicate `xml:id` values across a complete source collection
- avoid arbitrary code/model execution from user-supplied YAML
- method names/config schemas must resolve through a server-side registry
- protect export/download paths through artifact IDs rather than filesystem paths

Client filenames and media types are descriptive input, never authority for filesystem placement or import
semantics. The public request must declare source format, packaging, and profile from a closed validated set.
Detailed parser exceptions and source content do not cross the sanitized snapshot-failure boundary.

## LLM/external services

Default to local execution. If an external method is added, configuration and UI/API metadata must make data egress explicit.

## Audit

Record security-relevant and scholarly changes such as:

- snapshot imports
- run creation/cancellation
- annotation creation/supersession
- export creation
- user/role changes, including project-membership grants and revocations, which are currently logged with
  the acting administrator rather than kept as an append-only history

Do not log secrets or unnecessarily duplicate sensitive source content.


## Browser session

Authentication is provider-neutral. `AuthenticationBackend` in
[`api/authentication.py`](../src/gendertagger/api/authentication.py) is a protocol with two
operations, `authenticate` and `validate_csrf`. The application resolves one backend from process
state: `create_app` installs `DatabaseAuthenticationBackend` unless the caller supplies another, and
`RejectAllAuthenticationBackend` remains available as a backend that fails closed. Every backend
terminates into the same `CurrentUser` principal, which `GET /api/v1/me` returns without
persistence-only fields.

The production provider is a local, database-backed account system: admin-provisioned users,
Argon2id password hashes, and server-side revocable sessions, with no external identity provider and
no self-service registration or email-based password recovery. Administrators create accounts with
`gendertagger users create` and force a new password with `gendertagger users reset-password`; both
flag the account to change its password at next use. See
[ADR-0031](decisions/ADR-0031-local-database-authentication.md) for the exact schema, endpoints, and
cookie contract. Institutional SSO remains a later, additive `AuthenticationBackend` implementation.
The gateway throttles `POST /api/v1/auth/login` per client address: six attempts at once, then one every
12 seconds, answering further attempts with `429 rate_limited` in the API's error envelope and a
`Retry-After` header ([`deploy/proxy/nginx.conf`](../deploy/proxy/nginx.conf)). Every attempt costs an
Argon2id hash of about 64 MiB, so the limit guards the API's memory as well as passwords. It is per
address, not per account, and a stack reached without the gateway is not throttled; a per-username backoff
is recorded in [`22-future-development.md`](22-future-development.md).

`/api/v1` is assembled from three routers in [`api/router.py`](../src/gendertagger/api/router.py):

- Every route not listed below carries `require_csrf_protection` and `require_password_current`.
  Every request is therefore authenticated, and every unsafe method — anything outside `GET`, `HEAD`,
  `OPTIONS`, and `TRACE` — additionally requires backend-owned CSRF validation, returning
  `403 forbidden` when it fails. A local account still flagged to change its password receives
  `403 password_change_required`.
- `GET /me`, `GET /auth/session`, `POST /auth/logout`, and `POST /me/password` carry only
  `require_csrf_protection`, so a flagged account can learn about the flag and still reach the one route
  that clears it.
- `POST /auth/login` is the only unauthenticated route, since no session exists yet. A failed login
  returns a generic `401 invalid_credentials` whether or not the username exists.

Same-origin deployment uses secure HTTP-only session cookies with appropriate `Secure`,
`HttpOnly`, and `SameSite` settings, so authentication secrets are never stored in
JavaScript-accessible local or session storage.

Production does not require permissive CORS. Development CORS must be an explicit origin allow-list
and must never combine credentialed requests with `*`.

Annotation optimistic concurrency is a data-integrity control as well as a UX feature: stale review writes return `409 Conflict` rather than silently replacing another reviewer's decision.

## Session lifetime

Session lifetimes follow [ADR-0032](decisions/ADR-0032-sliding-session-lifetime.md). The login form's
"keep me signed in" checkbox, unchecked by default, chooses between two kinds of session:

| | Unchecked (default) | "Keep me signed in" |
|---|---|---|
| Cookies | Browser-session cookies, discarded when the browser closes | Persistent until the absolute limit |
| Idle limit | 24 hours (`GENDERTAGGER_SESSION_IDLE_SECONDS`) | 7 days (`GENDERTAGGER_SESSION_KEEP_SIGNED_IN_IDLE_SECONDS`) |
| Absolute limit from login | 30 days (`GENDERTAGGER_SESSION_MAX_LIFETIME_SECONDS`) | 30 days |

Each authenticated request slides the idle limit forward, never past the absolute limit, so an active
user is not signed out mid-work. The move is written back at most once per five minutes per session. Every
limit exceeds 20 hours, which places session expiry under WCAG 2.2.1's 20-hour exception; lowering a
limit to 20 hours or less removes that exemption and would require a pre-expiry warning in the client.

Browsers that restore the previous session keep browser-session cookies across a restart, so on a shared
machine the 24-hour server-side idle limit, not the browser closing, is what ends a forgotten unchecked
session. Background requests, such as polling a long-running run, count as activity.
