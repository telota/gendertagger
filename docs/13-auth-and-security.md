# Authentication and authorization

Authentication is required because the system supports imports, compute jobs, and scholarly annotations.

## Initial role model

Proposed v1 roles:

- `viewer`: read datasets/results
- `reviewer`: viewer + create annotations
- `operator`: reviewer + import snapshots, create runs/aggregations/exports
- `admin`: user/project administration and destructive administrative operations

Keep authorization in application services/dependencies rather than only hiding controls in the frontend.

## Project scoping

Design permissions so they can be scoped per project later even if v1 begins with global roles.

## Data safety

- validate uploaded XML and enforce size limits
- parse XML with secure settings; no external entity resolution
- sanitize filenames and never trust client paths
- avoid arbitrary code/model execution from user-supplied YAML
- method names/config schemas must resolve through a server-side registry
- protect export/download paths through artifact IDs rather than filesystem paths

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

For the planned same-origin Vue application, prefer secure HTTP-only session cookies so authentication secrets are not stored in JavaScript-accessible local/session storage. Use CSRF protection for state-changing requests and appropriate `Secure`, `HttpOnly`, and `SameSite` cookie settings.

The concrete identity provider remains open: local accounts and institutional OIDC/SSO can both terminate into the same `CurrentUser`/authorization abstraction. Machine/API clients may later use a separate bearer/OIDC flow.

Production should not require permissive CORS. Development CORS must be an explicit origin allow-list and must never combine credentialed requests with `*`.

Annotation optimistic concurrency is a data-integrity control as well as a UX feature: stale review writes return `409 Conflict` rather than silently replacing another reviewer's decision.
