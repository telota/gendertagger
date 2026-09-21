# Authentication and authorization

Authentication is required because the system supports imports, compute jobs, and scholarly annotations.

## Role model

`Role` in [`models/user.py`](../src/gendertagger/models/user.py) defines four global roles:

- `viewer`: read datasets/results
- `reviewer`: viewer + create annotations
- `operator`: reviewer + import snapshots, create runs/aggregations/exports
- `admin`: user/project administration and destructive administrative operations

`gendertagger.api.authorization` ranks the roles hierarchically, so a higher role grants every lower
capability, and exposes them as the `require_viewer`, `require_reviewer`, and `require_operator`
dependencies. Authorization therefore lives in application dependencies rather than only hiding
controls in the frontend.

Roles are global rather than per-project. Project-scoped permissions are recorded in
[`22-future-development.md`](22-future-development.md).

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
- user/role changes

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
Login rate limiting and lockout are not implemented yet; see
[`22-future-development.md`](22-future-development.md).

`/api/v1` is assembled from three routers in [`api/router.py`](../src/gendertagger/api/router.py):

- Every route not listed below carries `require_csrf_protection` and `require_password_current`.
  Every request is therefore authenticated, and every unsafe method — anything outside `GET`, `HEAD`,
  `OPTIONS`, and `TRACE` — additionally requires backend-owned CSRF validation, returning
  `403 forbidden` when it fails. A local account still flagged to change its password receives
  `403 password_change_required`.
- `GET /me`, `POST /auth/logout`, and `POST /me/password` carry only `require_csrf_protection`, so a
  flagged account can still reach the one route that clears the flag.
- `POST /auth/login` is the only unauthenticated route, since no session exists yet. A failed login
  returns a generic `401 invalid_credentials` whether or not the username exists.

Same-origin deployment uses secure HTTP-only session cookies with appropriate `Secure`,
`HttpOnly`, and `SameSite` settings, so authentication secrets are never stored in
JavaScript-accessible local or session storage.

Production does not require permissive CORS. Development CORS must be an explicit origin allow-list
and must never combine credentialed requests with `*`.

Annotation optimistic concurrency is a data-integrity control as well as a UX feature: stale review writes return `409 Conflict` rather than silently replacing another reviewer's decision.
