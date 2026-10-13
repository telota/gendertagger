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

The unversioned liveness endpoints `/health` and `/ready`, login, branding, and the explicitly public
classification surface require no account. Readiness checks the database and artifact root. All other
project and administrative resources retain the authentication and authorization boundary.

### Anonymous name classification

[ADR-0044](decisions/ADR-0044-public-name-classification.md) adds `GET /api/v1/public/methods` for the
deployment's selectable method descriptors and `POST /api/v1/public/classify`. Supply either
`{"name": "Maria", "methods": ["gender_guesser"]}` or
`{"names": ["Maria", "Heinrich"], "methods": ["gender_guesser"]}`. Method selection is optional;
it defaults to the public deployment allowlist. Per-method configuration belongs to the operator.
Up to 20 names with only quick local methods return a result and method/environment provenance with
`200`; larger batches and other method selections return a persisted classification job with `202`.
The maximum batch is 10,000 nonblank names, each at most 512 characters.

Save the acceptance response's `retrieval_token` and poll its `Location` using
`X-Classification-Token: <retrieval_token>`. The polling resource reports `queued`, `running`,
`completed`, or `failed` and includes the classification response only after completion. A token is
required for this anonymous resource to protect submitted names; it grants no project or account access.
Responses use `Cache-Control: no-store`. Raw diagnostics and deployment configuration secrets are never
returned. The authenticated `/api/v1/classify` endpoint keeps its existing contract.

### On-demand prediction caching and recovery

The authenticated synchronous endpoint and anonymous classification share a process-local,
thread-safe LRU cache, bounded to 50,000 predictions by default. A cache hit avoids adapter
execution. Cache identity includes the exact submitted name, method name, and a canonical JSON
digest of the complete method descriptor and validated, resolved configuration. Implementation
and normalization versions, the confidence contract, model selection, and lookup/model artifact
digests therefore separate outputs. Equivalent validated configurations share entries: JSON object
ordering and omitted fields equal to their defaults do not create separate identities.

Successful predictions, including the substantive `unknown` label, and normal `abstain`
outcomes are cacheable. Technical `error` predictions are not, whether the adapter returns them
or the service synthesizes them from a dependency, configuration, or execution failure. A later
request for the same name executes again and can observe recovery; the service adds neither an
automatic retry nor error expiry. Concurrent misses may execute independently. A late technical
failure cannot replace a recovered success or evict another cached prediction. Cache hits refresh
LRU recency, and only cacheable insertions can evict entries.

Insertion and retrieval deep-copy nested raw output and metadata, so adapter or consumer mutation
cannot change retained cache evidence. This cache changes only future executions. Completed
anonymous jobs retain their original predictions and provenance, including recorded technical
errors; recovery requires a new request and never rewrites or re-executes a terminal job.
HTTP `Cache-Control: no-store` remains a separate boundary for submitted names and job responses.

## Teams and delegated project membership

All paths below are relative to `/api/v1`. `GET /teams` returns a cursor-paginated, roster-free
`TeamSummary` collection for the caller's direct teams; a global administrator sees all teams. It requires
authentication and a current password, but grants no project access and never exposes a roster.

Global administrators use `GET, POST /admin/teams`, `PATCH, DELETE /admin/teams/{team_id}`,
`GET, POST /admin/teams/{team_id}/members`, and
`DELETE /admin/teams/{team_id}/members/{user_id}`. Team list pages are ordered by canonical slug then ID;
roster pages by normalized display name then user ID. All support server-side optional search, opaque cursor
pagination, and scope/filter-bound cursors. `POST /admin/teams` returns `201`; a duplicate canonical slug
returns `409 team_slug_conflict`. Team patches rename only the display name and preserve an immutable slug.
Empty deletion returns `204`; a nonempty team returns `409 team_not_empty`. Roster addition creates with
`201`, repeats idempotently with `200`, and rejects an inactive target with `409 inactive_user`.

`GET /projects/managed`, decided in
[ADR-0042](decisions/ADR-0042-management-only-project-discovery.md), returns the caller's current manager
assignments in slug order using opaque cursor pagination. Its `ManagedProjectSummary` contains only identity,
display identity, and roster-free team identity. It is not an accessible-project collection, does not alter
`GET /projects`, and exposes no scientific project data.

Project managers and global administrators use `GET /projects/{project_id}/members`,
`GET /projects/{project_id}/eligible-users`, project-membership writes, and manager transfer through the
delegated management guard. Those endpoints retain project-resource `404` hiding and do not grant ordinary
project access to a manager without a project role.

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

`GET /snapshots/{snapshot_id}/statistics` returns immutable inventory counts for a ready snapshot: total
people, GND coverage, and, where the import profile captured it, direct source-gender-element coverage,
canonical value distribution, and the GND/source-gender intersection. Source-gender fields are nullable as a
group so legacy and unsupported import profiles remain distinguishable from a measured zero. The endpoint
requires ordinary project viewer access and returns `409` until the snapshot is ready.

The bounded synchronous `/classify` operation is the deliberate exception to queued scientific execution. It
persists no Prediction; see
[ADR-0028](decisions/ADR-0028-synchronous-on-demand-classification-api.md).

## Artifact downloads

`GET /evaluations/{evaluation_id}/report` advertises the canonical `EvaluationReport` JSON schema in
OpenAPI while returning the persisted report bytes unchanged. The response model describes the artifact;
it is not a reserialization step. Artifact size and SHA-256 remain those recorded when the executor
stored the report.

Frontend report and export-manifest types come from the generated canonical schemas. Runtime parsers
still discriminate downloaded artifacts and reject malformed structure or unsupported vocabulary.
Generated TypeScript does not replace validation, and neither parser recomputes scientific metrics.
Export downloads retain their stored bytes, content type, filename, and checksum behavior.

## Collections

Potentially large or changing collections use opaque keyset cursors and stable server-side ordering. Clients
must not infer cursor contents or reuse a cursor with a different resource scope, filter set, or sort order.
Filtering, search, and sorting happen on the server, and collection summaries contain enough data to render a
list without one detail request per row.

Ordinary collection responses do not calculate total counts. When the product needs counts, expose a
domain-level summary resource rather than adding page-specific fields or forcing the client to download every
page.

### Project data availability

`GET /projects/{project_id}/data-availability` returns `ProjectDataAvailability`: the project ID,
`has_ready_snapshots`, and `has_completed_aggregations`. These are existence facts over the whole
project, independent of collection pagination and the optional working-aggregation pointer. A completed
aggregation is eligible regardless of its run's overall status; pending, failed, and cancelled
aggregations are not completed results. Reads never create resources or change the working pointer.

The endpoint requires ordinary project viewer access and follows project-resource `404` hiding.
Management authority alone does not grant access. The response describes persisted data, not navigation
permissions: clients combine it with the effective project role. A failed or pending read must not be
interpreted as an empty project.

### Snapshot, run, and aggregation filters

The snapshot, run, and aggregation collections retain newest-first `(created_at, id)` ordering and
the ordinary cursor envelope. Their optional filters are applied before pagination:

- `GET /projects/{project_id}/snapshots`: `status` (`DatasetSnapshotStatus`) and
  `has_completed_aggregations` (boolean), validated as `DatasetSnapshotListFilter`.
- `GET /snapshots/{snapshot_id}/runs`: `has_completed_aggregations` (boolean), validated as
  `RunListFilter`.
- `GET /runs/{run_id}/aggregations`: `status` (`AggregationExecutionStatus`), validated as
  `AggregationExecutionListFilter`.

Omitting a filter matches all values; `has_completed_aggregations=false` matches resources without
any completed aggregation. Completed-result existence is scoped to the owning snapshot or run,
independent of the run's overall lifecycle state and the project's working-result pointer. Filters
never create an aggregation. A cursor binds the complete normalized filter tuple and parent scope;
changing or removing a filter requires starting a new traversal. Existing unfiltered cursors remain
valid. Ordinary project viewer authorization and resource hiding apply to each collection.

### Method execution results

`GET /runs/{run_id}/executions/{method_execution_id}/results` returns a cursor-paginated,
TEI-identifier-ordered `MethodExecutionResult` projection for every person in the run snapshot.
It is an execution-owned read resource: ordinary run viewer authorization applies, and an execution
that is absent or belongs to another run returns `404 resource_not_found`.

Each row contains person identity and name projections, a `result_state`, and a nullable bounded
prediction summary. `missing` means no immutable Prediction row was persisted for that person; it
is distinct from a persisted `abstain`, a persisted technical `error`, and a successful result whose
canonical label is `unknown`. Present summaries include only label, status, method-specific confidence,
and raw label. Raw method output and normalization metadata remain persisted provenance and are not
included in this potentially large collection.

The optional `q`, `result_state`, and `label` filters run on the server before pagination. `q` matches
TEI identifier and imported name projections. Cursors bind the run, execution, and normalized filters,
with `(tei_id, person_record_id)` ordering. A changed filter starts a new traversal.

## Review items

`GET /snapshots/{snapshot_id}/annotation-items` returns a cursor-paginated collection of
`SnapshotAnnotationItem`: imported identity and name fields plus the current human action, label,
workflow state, and revision. It requires a ready snapshot and ordinary project viewer access, without
requiring a run or aggregation. `q`, repeated `workflow_states`, and optional `human_label` filters run
on the server; cursors bind every filter and the snapshot, with stable `(tei_id, person_record_id)`
ordering. `GET /snapshots/{snapshot_id}/annotation-items/{tei_id}` reads an exact record independently
of list pagination. Unannotated records have revision zero and null decision fields; deferred records
have a null human label. These resources contain no machine evidence. Reviewer writes continue through
`POST /annotations`, using the same snapshot/person revision stream and an optional machine-result
reference. See [annotation before classification](09-annotation-and-review.md#annotation-before-classification).

`review-items` is a domain query resource, not a page-specific endpoint. It projects the person, aggregation
evidence, final decision, and current review revision needed for uncertainty-first review. Query filters and
sorts are validated contracts, and the cursor is scoped to their complete normalized tuple.

`GET /review-items` optionally accepts `tei_id` for an exact, case-sensitive person identifier
within the selected aggregation's snapshot. This lookup applies before pagination and is distinct
from the substring search `q`; supplying both requires both to match. Exact identity participates in
cursor scope, while omitting it preserves existing cursors. The ordinary aggregation authorization
and completed-result prerequisites also apply to exact lookups.

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

## Game rounds

Game mode is a project-level opt-in. `PUT /projects/{project_id}/game-mode` requires the project
`operator` role, accepts `ProjectGameModeUpdate`, and returns the updated `AccessibleProject`. New projects
default to disabled.

When enabled, reviewers submit a completed round through `POST /projects/{project_id}/game-rounds`. The
idempotent command supplies a client-generated round ID, a completed aggregation ID, one of the fixed round
sizes `10`, `20`, or `50`, and the ordered IDs of answers already saved through `POST /annotations`. The
service accepts only distinct `verify` or `correct` annotations by the authenticated reviewer for that
aggregation, ensures each person occurs once and each annotation contributes to at most one round, and derives
the official score as ten points per accepted annotation. Browser timing, skips, and streak state are neither
accepted nor persisted by this endpoint.

`GET /projects/{project_id}/game-leaderboard?round_size={10|20|50}` requires ordinary viewer access and
returns at most one best round per reviewer for that comparable size. Both round creation and leaderboard
reads return `409 game_mode_disabled` while the project flag is off. Disabling the feature retains prior
rounds and never changes annotations, review order, or final decisions. See
[`09-annotation-and-review.md`](09-annotation-and-review.md#game-mode).

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

`POST /admin/users/{user_id}/revoke-sessions` accepts no body and returns `204 No Content`. It is restricted
to global administrators and carries the standard CSRF and password-current gates. The service validates that
the target exists and has a local credential in its mutation transaction, then revokes every active target
session without changing its password, activation state, roles, or forced-password-change flag. An absent or
non-local target returns `404 resource_not_found`; a target with no active sessions still succeeds. An
administrator may target their own account: the current session is revoked after authentication, so the `204`
response completes but the next authenticated request must sign in again.

## Personal presentation preferences

[ADR-0043](decisions/ADR-0043-account-level-user-preferences.md) adds self-service account preferences,
and [ADR-0050](decisions/ADR-0050-guided-and-advanced-interface-mode-preference.md) adds the
`interface_mode` field. Paths below are relative to `/api/v1`.

| Endpoint | Request | Response |
|---|---|---|
| `GET /me/preferences` | None | `200 UserPreferences` |
| `PATCH /me/preferences` | `UserPreferencesUpdate`: required `expected_revision` plus nonempty partial preference fields | `200 UserPreferences` |

Ownership is exclusively the authenticated principal's existing active local account. Neither route accepts
an owner ID or requires a global/project role. Both require a resolved password-current session and return
`Cache-Control: no-store`; PATCH also uses the shared CSRF mechanism. Unresolved or non-local accounts use
`401 authentication_required`, forced-password accounts use `403 password_change_required`, and invalid CSRF
uses the existing `403 forbidden` envelope.

The default resource for an account without a preferences row is
`{"locale": null, "theme": "system", "desktop_sidebar_collapsed": false, "interface_mode": "guided",
"revision": 0}`.
GET does not initialize storage. PATCH preserves omitted fields, and explicit `locale: null` clears an
explicit locale without resolving the browser's effective language. Null theme/collapse, unknown fields,
invalid values, and empty updates receive `422 validation_error`.

A changed save increments the revision and returns the canonical committed resource. A matching-revision
no-op returns the existing revision and does not create an absent row. Stale requests, including stale
no-ops, receive `409 preferences_revision_conflict` with expected/current revisions in the established error
details. Parent-account locking makes concurrent initial writes follow the same conflict semantics.
Personal presentation preferences never use `/admin/settings` or project/scientific configuration.

## Administrative settings

The two backend slices of [ADR-0040](decisions/ADR-0040-administrative-branding-overrides.md) are
implemented and listed in generated OpenAPI. All paths are relative to `/api/v1`.

| Endpoint | Request | Success | Status |
|---|---|---|---|
| `GET /admin/settings` | None | `200 AdminSettings` | Delivered |
| `PATCH /admin/settings` | `AdminSettingsUpdate` with `expected_revision` and nonempty partial `branding` | `200 AdminSettings` | Delivered |
| `POST /admin/settings/reset` | `AdminSettingsReset` with `expected_revision` and nonempty distinct `fields` | `200 AdminSettings` | Delivered |

All operations require a global administrator who has completed any forced password change. Unsafe operations
use existing CSRF protection; every response uses `Cache-Control: no-store`. `AdminSettings` exposes the
revision, effective `BrandingInfo`, current deployment fallbacks for the six editable fields, and overridden
field names. It never serializes `AppSettings` wholesale. See the
[canonical contracts](03-pydantic-contracts.md#administrative-settings-contracts).

Updates preserve omitted overrides. Explicit `null` clears nullable values, and `editors: []` clears the
editor list; these remain overrides. Reset removes overrides for explicitly selected allowlisted fields,
revealing the current environment/application fallback. There are no arbitrary keys, paths, or wildcard
resets. Both commands validate and apply all requested changes atomically under the same revision check. A
matching-revision no-op retains its revision; a stale command still conflicts even if its requested values
match. Setting a previously inherited value as an explicit override is a change even when the value equals
the fallback.

Errors use the shared envelope: `401 authentication_required`, existing `403 forbidden` or
`403 password_change_required` gates, `422 validation_error` for invalid values or commands,
`409 settings_revision_conflict` with safe expected/current revision details for stale writes, and
`503 settings_unavailable` for unavailable settings storage. Failed mutations return no success response
or success log. Reset-to-default reveals the serving process's current fallback, not the value from the
original deployment.

Import limits remain deployment-managed; existing upload-limit discovery continues through
`GET /snapshot-upload-limits`. Session policy, infrastructure, secrets, filesystem paths, worker tuning,
and scientific configuration are outside this settings API. `initiatives` and `legal_entity` remain
read-only branding, and logo behavior is unchanged.

## Branding surface

`GET /branding` and `GET /branding/logo` are unauthenticated, need no grant, and carry no scientific or project-scoped data ([ADR-0036](decisions/ADR-0036-institution-branding-configuration.md)). They exist so the client's footer, start page, and legal notice can be reachable without a session and configured per deployment instead of hard-coded.

- `GET /branding` returns effective `BrandingInfo`, resolving committed stored overrides before the operator's
  startup-loaded `GENDERTAGGER_BRANDING__*` fallback. It remains unauthenticated, preserves its response
  schema, reads settings storage for every request, returns `Cache-Control: no-store`, and maps unavailable
  settings storage to `503 settings_unavailable` without substituting fallback branding.
- `GET /branding/logo` remains filesystem-backed and streams the configured logo file with its detected media
  type, or `404 resource_not_found` when no `logo_path` is set or the file is missing. `BrandingInfo.logo_url`
  remains the literal path `/api/v1/branding/logo` when the file exists and `null` otherwise.

Saved values take effect on subsequent server reads without a restart. Already-open frontend views require a
refresh or component remount; active-view refresh behavior remains pending with the frontend slice.

## CORS

Production uses one origin for the Vue client and FastAPI, making general CORS unnecessary. Development may
explicitly allow the Vite origin. Wildcard origins are forbidden with credentialed requests.

## OpenAPI change workflow

OpenAPI changes are public contract changes. The snapshot check and generated frontend types must change
together, and reviewers inspect both diffs. Exact regeneration and validation commands are maintained in
[`CONTRIBUTING.md`](../CONTRIBUTING.md); do not maintain handwritten transport models.
