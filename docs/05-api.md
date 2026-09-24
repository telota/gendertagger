# FastAPI design

## Principles

FastAPI is the canonical public interface. The browser UI, remote CLI operations, and external edition
integrations consume the same application semantics under `/api/v1`.

Favor resource-oriented endpoints over classifier-specific or page-specific RPC endpoints. A screen is not
an API resource; a Run, ReviewItem, Annotation, Export, or Evaluation is. The API exposes explicit Pydantic
request and response models and never SQLAlchemy instances.

## Public contract

Generated OpenAPI is the authoritative endpoint, parameter, payload, response, and status-code inventory. It
is available from the running service at `/openapi.json` and through `/docs`. The committed snapshot at
[`contracts/openapi-v1.json`](../contracts/openapi-v1.json) detects unintended contract changes and
drives the generated TypeScript transport types.

This document records behavioral rules that are not usefully conveyed by an endpoint catalogue. Contract
model rationale lives in [`03-pydantic-contracts.md`](03-pydantic-contracts.md), and browser-specific use of
the API lives in [`17-frontend-integration.md`](17-frontend-integration.md).

## JSON conventions

Public `/api/v1` JSON uses:

- `snake_case` field names;
- stable lowercase string enum values;
- UUID strings for service resource IDs;
- canonical TEI `xml:id` strings for person identity within a project;
- timezone-aware ISO 8601 UTC timestamps;
- `null` for absent optional values, never magic strings.

The scientific `unknown` label is never represented by `null`. API errors use one documented Pydantic
envelope with a stable code, human-readable message, optional details, and request ID.

## Resource and authorization semantics

Resources are addressed by durable domain IDs. Predictions are immutable method outputs and are exposed only
through their owning execution or aggregation result; they have no mutable public collection. Annotation
history remains append-only and exposes the current review revision alongside the full superseding chain.

Every project representation includes `current_user_role`. Project collections contain only projects visible
to the caller. A project-scoped resource that does not exist and one owned by an inaccessible project both
return `404 resource_not_found`; a project member below the required role receives `403 forbidden`. The full
role model and password-change restrictions are defined in
[`13-auth-and-security.md`](13-auth-and-security.md).

The project working-aggregation pointer selects the completed aggregation summarized by its review surfaces.
Changing it is an explicit project operation; creating an aggregation never moves it implicitly. See
[ADR-0035](decisions/ADR-0035-project-working-aggregation.md).

Only the unversioned liveness endpoints `/health` and `/ready` are public without authentication. Readiness
checks the database and artifact root.

## Long-running commands

Snapshot imports, runs, method executions, aggregations, evaluations, and exports are persisted asynchronous
resources. Their command endpoints return `202 Accepted` where work has been newly accepted and expose the
persisted resource, never a Celery task ID.

Acceptance atomically stores the domain resource and a typed dispatch-outbox intent. The API does not publish
directly to Redis. A successful response therefore confirms durable application state, not immediate broker
delivery; the dispatch coordinator relays and reconciles the intent asynchronously. Task envelopes contain
only validated resource identifiers.

Clients observe lifecycle state through ordinary `GET` requests. A failed resource exposes a sanitized
diagnostic and never a partial result set. Aggregation creation is repeat-safe under the matching rules in
[ADR-0034](decisions/ADR-0034-reuse-matching-aggregation-on-creation.md); retrying a matching active or
completed request returns the existing resource.

Snapshot acceptance, supported import combinations, and artifact guarantees are defined in
[`08-ingestion-and-export.md`](08-ingestion-and-export.md). Queue and retry behavior is defined in
[`06-task-queue.md`](06-task-queue.md).

`GET /snapshots/{snapshot_id}/source-members` exposes the immutable ordered source manifest as
`SnapshotSourceMember` records. It provides logical filenames, SHA-256 digests, byte sizes, media types, and
ordinals for provenance views without serving source bytes or storage locations.

`GET /snapshots/{snapshot_id}/people/{tei_id}` reads one `PersonRecord` by its snapshot-scoped canonical TEI
identity. It supports stable detail URLs without requiring clients to search cursor pages.

The bounded synchronous `/classify` operation is the deliberate exception to queued scientific execution. It
persists no Prediction; see
[ADR-0028](decisions/ADR-0028-synchronous-on-demand-classification-api.md).

## Collections

Potentially large or changing collections use opaque keyset cursors and stable server-side ordering. Clients
must not infer cursor contents or reuse a cursor with a different resource scope, filter set, or sort order.
Filtering, search, and sorting happen on the server, and collection summaries contain enough data to render a
list without one detail request per row.

Ordinary collection responses do not calculate total counts. When the product needs counts, expose a
domain-level summary resource rather than adding page-specific fields or forcing the client to download every
page.

## Review items

`review-items` is a domain query resource, not a page-specific endpoint. It projects the person, aggregation
evidence, final decision, and current review revision needed for uncertainty-first review. Query filters and
sorts are validated contracts, and the cursor is scoped to their complete normalized tuple.

The uncertainty order is the versioned `review_triage_v1` strategy. A completed aggregation is immutable, so
annotation activity does not reorder records between pages. See
[`09-annotation-and-review.md`](09-annotation-and-review.md) and
[ADR-0022](decisions/ADR-0022-uncertainty-first-review-ordering.md).

### Review summary

The aggregation review summary groups the complete result set by certainty tier, agreement tier, current
review state, final label, and current review action. Screens derive queue sizes and reviewed/corrected counts
from these groups rather than paging through results.

The summary uses the same final-decision resolution and review-state semantics as `review-items` and the
`human_overrides` export policy. It remains a domain projection; it must not acquire screen-specific fields.

## Progress and events

Run progress is always recoverable from persisted Run and MethodExecution resources. Server-Sent Events are a
convenience view for live updates, never the authoritative state channel. A disconnected client reconnects
and refreshes current state through ordinary `GET` requests.

The stream uses these stable event names:

- `run.state_changed` and `run.progress`;
- `method_execution.state_changed` and `method_execution.progress`;
- `run.completed` and `run.failed` for terminal state.

Payloads are Pydantic contracts. Persisted event replay and `Last-Event-ID` resume are deferred in
[`22-future-development.md`](22-future-development.md).

## Errors and concurrency

Framework validation failures are normalized into the shared public error envelope where practical. Worker
tracebacks and sensitive source or model content are never exposed to ordinary clients.

Immutable resources do not need client-side locks. Annotation commands use optimistic concurrency through a
monotonically increasing review revision scoped to one person in one snapshot. A stale write returns
`409 annotation_conflict`; the client reloads the history/current-state resource and never overwrites an
annotation row.

## Browser authentication

The same-origin browser uses secure HTTP-only session cookies and a readable CSRF cookie mirrored into the
request header for unsafe methods. All `/api/v1` routes except login authenticate through the shared
dependency; unsafe requests additionally require CSRF validation. Local-account login, logout, forced password
change, session lifetime, provisioning, and project-role behavior are defined in
[`13-auth-and-security.md`](13-auth-and-security.md),
[ADR-0031](decisions/ADR-0031-local-database-authentication.md), and
[ADR-0032](decisions/ADR-0032-sliding-session-lifetime.md).

Authorization is enforced by FastAPI dependencies and application services. UI visibility rules are a user
experience aid, never the security boundary.

## Administrative user directory

`GET /admin/users` is restricted to global administrators and returns local accounts in normalized-username
order. It supports server-side username/display-name search and opaque cursor pagination. The
administrator-facing projection contains identity, global roles, activation state, forced-password-change
state, and creation time; it never exposes password hashes or session data.

`POST /admin/users` accepts a display name, normalized local username, and global roles. It creates an
active account with a server-generated temporary password and `must_change_password=true`, then returns
`201 Created` with the account and that password. The password is disclosed only in that response, which
sets `Cache-Control: no-store`; it is never logged. A duplicate normalized username returns
`409 username_conflict`.

`PATCH /admin/users/{user_id}` accepts only `display_name`, `roles`, and `is_active`; omitted fields remain
unchanged, while `null`, unknown fields, blank display names, and a username are rejected. It returns the
updated `AdminUser`, or `404 resource_not_found` when the account is absent or non-local. It returns stable
`409` account-state codes when a patch would deactivate the acting administrator, remove the actor's own
`admin` role, or violate a concurrently revalidated administrator invariant. Deactivation revokes every
session in the same transaction; reactivation never restores them. See
[ADR-0039](decisions/ADR-0039-administer-local-accounts-over-http.md).

`POST /admin/users/{user_id}/reset-password` accepts no body and returns `200 OK` with an
`AdminUserPasswordResetResult`. It is restricted to global administrators and carries the standard CSRF and
password-current gates. The service validates that the target exists and has a local credential in its mutation
transaction, replaces only its password hash, sets `must_change_password=true`, and revokes every target
session in that transaction. A reset never changes activation state; an absent or non-local target returns
`404 resource_not_found`. Each success returns a fresh server-generated temporary password only in that
non-cacheable (`Cache-Control: no-store`) response and never logs it.

## Branding surface

`GET /branding` and `GET /branding/logo` are unauthenticated, need no grant, and carry no scientific or project-scoped data ([ADR-0036](decisions/ADR-0036-institution-branding-configuration.md)). They exist so the client's footer, start page, and legal notice can be reachable without a session and configured per deployment instead of hard-coded.

- `GET /branding` returns `BrandingInfo`, built from the operator's `GENDERTAGGER_BRANDING__*` settings. Every field is `null` when the operator has not configured it; the client renders that as an explicit "not configured" state.
- `GET /branding/logo` streams the configured logo file with its detected media type, or `404 resource_not_found` when no `logo_path` is set or the file is missing. `BrandingInfo.logo_url` is the literal path `/api/v1/branding/logo` when the file exists and `null` otherwise, so the client never constructs the path itself.

## CORS

Production uses one origin for the Vue client and FastAPI, making general CORS unnecessary. Development may
explicitly allow the Vite origin. Wildcard origins are forbidden with credentialed requests.

## OpenAPI change workflow

OpenAPI changes are public contract changes. The snapshot check and generated frontend types must change
together, and reviewers inspect both diffs. Exact regeneration and validation commands are maintained in
[`CONTRIBUTING.md`](../CONTRIBUTING.md); do not maintain handwritten transport models.
