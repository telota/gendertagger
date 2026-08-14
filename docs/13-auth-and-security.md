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

For the planned same-origin Vue application, prefer secure HTTP-only session cookies so authentication secrets are not stored in JavaScript-accessible local/session storage. Use CSRF protection for state-changing requests and appropriate `Secure`, `HttpOnly`, and `SameSite` cookie settings.

The concrete identity provider remains open: local accounts and institutional OIDC/SSO can both terminate into the same `CurrentUser`/authorization abstraction. Machine/API clients may later use a separate bearer/OIDC flow.

Production should not require permissive CORS. Development CORS must be an explicit origin allow-list and must never combine credentialed requests with `*`.

Annotation optimistic concurrency is a data-integrity control as well as a UX feature: stale review writes return `409 Conflict` rather than silently replacing another reviewer's decision.
