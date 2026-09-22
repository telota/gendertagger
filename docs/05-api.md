# FastAPI design

## Principles

FastAPI is the canonical public interface. The browser UI, CLI where remote operation is desired, and external edition integrations consume the same application semantics.

The public API is versioned under `/api/v1`.

Favor resource-oriented endpoints over classifier-specific or page-specific RPC endpoints. A Vue screen is not an API resource; a Run, ReviewItem, Annotation, Export, or Evaluation is.

The API exposes explicit Pydantic request/response models and never SQLAlchemy instances. OpenAPI is a
public machine-readable contract, and a committed schema snapshot pins it against unintended change.

## JSON conventions

Public `/api/v1` JSON uses:

- `snake_case` field names;
- stable lowercase string enum values;
- UUID strings for service resource IDs;
- canonical TEI `xml:id` strings for person identity within a project;
- timezone-aware ISO 8601 UTC timestamps;
- `null` for absent optional values, never magic strings.

The scientific `unknown` label is never represented by `null`.

## Resource outline

[`gendertagger.api.router`](../src/gendertagger/api/router.py) composes the complete versioned surface from
three routers under the `/api/v1` prefix, which differ only in their authentication requirements (see
below). The following table is the whole public API:

| Method | Path | Success status | Access |
|---|---|---|---|
| `POST` | `/api/v1/projects` | `201` | global operator |
| `GET` | `/api/v1/projects` | `200` | any authenticated user; lists the caller's projects |
| `GET` | `/api/v1/projects/{project_id}` | `200` | project viewer of `project_id` |
| `GET` | `/api/v1/projects/{project_id}/members` | `200` | global admin |
| `PUT` | `/api/v1/projects/{project_id}/members/{user_id}` | `200` | global admin |
| `DELETE` | `/api/v1/projects/{project_id}/members/{user_id}` | `204` | global admin |
| `POST` | `/api/v1/projects/{project_id}/snapshots` | `202` | project operator of `project_id` |
| `GET` | `/api/v1/projects/{project_id}/snapshots` | `200` | project viewer of `project_id` |
| `GET` | `/api/v1/snapshots/{snapshot_id}` | `200` | project viewer of `snapshot_id` |
| `GET` | `/api/v1/snapshots/{snapshot_id}/people` | `200` | project viewer of `snapshot_id` |
| `GET` | `/api/v1/snapshots/{snapshot_id}/runs` | `200` | project viewer of `snapshot_id` |
| `POST` | `/api/v1/runs` | `202` | project operator of body `dataset_snapshot_id` |
| `GET` | `/api/v1/runs/{run_id}` | `200` | project viewer of `run_id` |
| `GET` | `/api/v1/runs/{run_id}/executions` | `200` | project viewer of `run_id` |
| `POST` | `/api/v1/runs/{run_id}/executions` | `202` | project operator of `run_id` |
| `GET` | `/api/v1/runs/{run_id}/events` | `200` (SSE) | project viewer of `run_id` |
| `POST` | `/api/v1/runs/{run_id}/aggregations` | `202`, or `200` when reused | project operator of `run_id` |
| `GET` | `/api/v1/runs/{run_id}/aggregations` | `200` | project viewer of `run_id` |
| `GET` | `/api/v1/runs/{run_id}/evaluations` | `200` | project viewer of `run_id` |
| `GET` | `/api/v1/runs/{run_id}/exports` | `200` | project viewer of `run_id` |
| `GET` | `/api/v1/aggregations/{aggregation_id}` | `200` | project viewer of `aggregation_id` |
| `GET` | `/api/v1/aggregations/{aggregation_id}/results` | `200` | project viewer of `aggregation_id` |
| `GET` | `/api/v1/aggregations/{aggregation_id}/results/{result_id}` | `200` | project viewer of `aggregation_id` |
| `GET` | `/api/v1/aggregations/{aggregation_id}/results/{result_id}/predictions` | `200` | project viewer of `aggregation_id` |
| `GET` | `/api/v1/aggregations/{aggregation_id}/review-summary` | `200` | project viewer of `aggregation_id` |
| `GET` | `/api/v1/review-items` | `200` | project viewer of query `aggregation_id` |
| `GET` | `/api/v1/annotations` | `200` | project viewer of query `snapshot_id` |
| `POST` | `/api/v1/annotations` | `201` | project reviewer of body `snapshot_id` |
| `POST` | `/api/v1/evaluations` | `202` | project operator of body `run_id` |
| `GET` | `/api/v1/evaluations/{evaluation_id}` | `200` | project viewer of `evaluation_id` |
| `GET` | `/api/v1/evaluations/{evaluation_id}/report` | `200` | project viewer of `evaluation_id` |
| `POST` | `/api/v1/exports` | `202` | project operator of body `run_id` |
| `GET` | `/api/v1/exports/{export_id}` | `200` | project viewer of `export_id` |
| `GET` | `/api/v1/exports/{export_id}/download` | `200` | project viewer of `export_id` |
| `POST` | `/api/v1/classify` | `200` | any global role or project membership |
| `GET` | `/api/v1/methods` | `200` | any global role or project membership |
| `GET` | `/api/v1/me` | `200` | any authenticated user |
| `POST` | `/api/v1/me/password` | `204` | any authenticated user |
| `GET` | `/api/v1/auth/session` | `200` | any authenticated user |
| `POST` | `/api/v1/auth/login` | `200` | none (unauthenticated) |
| `POST` | `/api/v1/auth/logout` | `204` | any authenticated user |

Predictions have no public collection of their own. A run's per-method outputs are read through its
executions and through the aggregated results that summarize them.
`GET /aggregations/{aggregation_id}/results/{result_id}/predictions` returns, for the person behind one
result, one `ResultMethodPrediction` per method execution the aggregation selected, in selection order. Each
carries the method's immutable `PredictionResult`, including its raw output and normalization provenance,
or a null `prediction` when the execution persisted none for that person. Absence therefore stays distinct
from `abstain` and `error`. Each `method_confidence` is method-specific and is not comparable across methods.

`GET /annotations?snapshot_id=&tei_id=` returns one person's `AnnotationHistory`: the current review state
and every annotation that ever applied to the person, newest first, each with its reviewer's display name.
Its `revision` is the `expected_revision` for the next `POST /annotations`, so a client recovering from
`409 annotation_conflict` reloads this one resource. The read takes a shared lock on the person so that the
state and the chain always describe the same revision.

Every route except `POST /auth/login` carries `Depends(require_csrf_protection)`, so the dependency runs
before any handler body. Because that dependency in turn depends on `require_authenticated_user`, the
`/api/v1` boundary is fail-closed for reading as well as writing: an unauthenticated request is rejected
with `401` even on a safe method. `require_csrf_protection` additionally validates the browser session for
unsafe methods; `GET`, `HEAD`, `OPTIONS`, and `TRACE` return early without a CSRF check. Every route except
`GET /me`, `GET /auth/session`, `POST /me/password`, and `POST /auth/logout` also carries
`require_password_current`, which returns `403 password_change_required` while a local account still owes a
password change. Authorization then narrows the capability per route
([ADR-0033](decisions/ADR-0033-project-scoped-membership-roles.md)). A project-scoped route resolves the
project that owns the identifier named in the table — a path parameter, or the body or query field shown —
and requires the caller's role in that project to be at least the listed project role. Project roles are
hierarchical, so a project operator satisfies a reviewer route, and a global admin holds operator in every
project. A caller with no role in the owning project receives `404 resource_not_found`, exactly as for a
resource that does not exist; a member below the least role receives `403 forbidden`. The remaining routes
check a global role, any grant, or authentication alone. [`13-auth-and-security.md`](13-auth-and-security.md)
defines the role model.

Every project representation — from `POST /projects`, `GET /projects`, and `GET /projects/{project_id}` — is
an `AccessibleProject`: the `Project` fields plus `current_user_role`, the caller's effective project role,
so a client can scope its controls without a second request. `GET /projects` is cursor-paginated in slug
order and returns only the projects where the caller has a role.

All three routers declare `ApiErrorEnvelope` as the documented response model for `400`, `401`, `403`,
`404`, `409`, `413`, `422`, and `500` across every route, so the error contract is uniform in OpenAPI.

Only the unversioned liveness endpoints `GET /health` and `GET /ready` sit outside the router, and
therefore outside authentication; `/ready` probes the database and the artifact root.

## Long-running commands

Imports, runs, method execution, aggregation, evaluations, and exports are asynchronous resources. Do not keep
an HTTP request open while scientific computation executes.

Representative flow:

```text
POST /api/v1/runs
  -> 202 Accepted
  -> Run(id=..., status="created")

POST /api/v1/runs/{run_id}/executions
  -> 202 Accepted
  -> Run(id=..., status="queued")

GET /api/v1/runs/{run_id}
  -> persisted current state
```

Return domain resource IDs, never Celery task IDs. Celery is an internal execution mechanism and can change without changing the public API. The committed OpenAPI snapshot test asserts that `task_id`, `queue_name`, `worker_metadata`, and `storage_uri` never appear in the public schema.

Accepting an asynchronous command atomically persists its domain resource and one typed outbox intent in
PostgreSQL. `DispatchTarget` in [`gendertagger.models.dispatch`](../src/gendertagger/models/dispatch.py)
enumerates the five things a dispatch can own: `task_batch`, `aggregation_execution`, `dataset_snapshot`,
`evaluation_execution`, and `export`. Each entry carries only its small validated identifier envelope. The
FastAPI process does not publish those messages to Redis. A `202 Accepted` response therefore confirms
durable application state and dispatch intent, not immediate broker delivery; the `dispatch-coordinator`
service relays and reconciles that intent asynchronously.

## Representative commands

### Create snapshot import

`POST /api/v1/projects/{project_id}/snapshots`

The endpoint consumes multipart form data. Repeat the `source` file part for a loose TEI collection; all other
supported combinations require exactly one part. Three form fields select the import contract explicitly:

| Field | Values | Default |
|---|---|---|
| `source_format` | `tei`, `csv`, `xlsx`, `json` | `tei` |
| `packaging` | `single`, `loose`, `zip`, `tar_gz` | `single` |
| `profile` | a compatible versioned TEI or tabular profile | `tei_p5_person_register_v3` |

TEI supports every packaging value. CSV, XLSX, and JSON support only `single` with
`tei_equivalent_person_register_v1`. The server does not infer these semantic choices from a filename or
client-provided media type. Incompatible values, an incorrect part count, unsafe or colliding logical names,
and non-XML loose member names are request validation errors.

The API streams, bounds, and hashes every exact upload into immutable shared artifact storage. For loose TEI,
it also creates a deterministic source manifest. It then atomically persists all Artifact records, ordered
source-member provenance, the pending DatasetSnapshot, and typed outbox intent. Only after those durable steps
does it return `202 Accepted` with the pending snapshot. Upload transfer, validation of multipart member names,
storage, hashing, and the short acceptance transaction may therefore take request time; source parsing,
archive or workbook inspection, and PersonRecord persistence do not.

Clients poll `GET /api/v1/snapshots/{snapshot_id}` for `ready` or `failed`. The worker's `importing` state is
transaction-local, so API readers continue to see `pending` until the complete projection commits atomically.
An invalid document, archive, workbook, or record shape is accepted as durable work and later produces a
failed snapshot with a sanitized diagnostic; content is not parsed inside the initial request. Broker downtime
leaves the pending import recoverable through the outbox. The response never contains a Celery task ID,
artifact storage URI, or filesystem path. Artifact-reference imports remain outside the public contract. See
[ADR-0020](decisions/ADR-0020-asynchronous-snapshot-import-outbox.md) and
[ADR-0021](decisions/ADR-0021-versioned-multi-format-snapshot-ingestion.md).

### Create run

`POST /api/v1/runs`

`RunCreateRequest` takes exactly two fields:

- `dataset_snapshot_id`;
- `config`, an inline `RunConfig` envelope of `methods`, `aggregation`, and `execution`.

The method registry resolves every method config before persistence, so an unknown method or an invalid
config contract fails with `422` and code `validation_error`. A snapshot that is not `ready` fails with
`409` and code `resource_conflict`. The result is a persisted Run in status `created`, carrying the
canonical SHA-256 hash of its resolved config. Creation does not schedule work; `created` is a distinct
state from `queued`.

### Start/run executions

State transitions, not method-named endpoints, drive execution:

`POST /api/v1/runs/{run_id}/executions`

The scheduler accepts only a run in status `created`, moves it to `queued`, and atomically persists its
method executions, task batches, and dispatch intents. The command then returns the persisted run. Broker
outages do not turn an otherwise successful durable scheduling command into an HTTP failure. Re-issuing the
command against an already scheduled run returns `409` with code `resource_conflict`.

`GET /api/v1/runs/{run_id}/executions` lists the same run's executions as `MethodExecutionSummary`
objects. The service returns the internal `MethodExecution`, and the declared response model narrows both
the payload and the OpenAPI schema, so queue names and worker identities never reach a client.

### Aggregate

`POST /api/v1/runs/{run_id}/aggregations`

Aggregation must be independently rerunnable without classifier execution. The command selects the exact
completed MethodExecutions, then atomically creates a `queued` `AggregationExecution` and its CPU-queue outbox
intent. It returns that resource with `202 Accepted`, never a Celery task ID, and does not compute results in
the request.

Repeating a command is safe ([ADR-0034](decisions/ADR-0034-reuse-matching-aggregation-on-creation.md)). An
aggregation matches when it has the same run, strategy, configuration hash, and exact ordered
`method_execution_ids`, and its status is `pending`, `queued`, `running`, or `completed`. When a match
exists, the command returns it unchanged with `200 OK` and creates neither an aggregation nor dispatch
intent. A `failed` or `cancelled` aggregation never matches, so the same request after a failure creates a
fresh attempt. Selection order is part of the match, so a client that wants repeated requests to match sends
the executions in a stable order, such as the order `GET /runs/{run_id}/executions` returns. Concurrent
identical requests serialize on a lock of the run row, so they return one aggregation between them.

Clients read lifecycle state through:

```text
GET /api/v1/aggregations/{aggregation_id}
```

Only `status=completed` guarantees that the results collection contains exactly one immutable result for every
person in the run snapshot. `status=failed` includes a sanitized diagnostic and exposes no partial result set.
Broker downtime leaves the resource safely queued for the coordinator. See
[ADR-0016](decisions/ADR-0016-asynchronous-aggregation-outbox.md).

Results are read as a cursor page through `GET /api/v1/aggregations/{aggregation_id}/results`, and one
immutable result is addressable under its owning aggregation as
`GET /api/v1/aggregations/{aggregation_id}/results/{result_id}`.

### Annotate

`POST /api/v1/annotations`

Creates a new immutable human decision. The command contains the review revision observed by the client. A stale revision returns `409 Conflict`; no historical annotation is overwritten.

### Evaluate

`POST /api/v1/evaluations`

`EvaluationCreateRequest` selects one `run_id`, a versioned `definition` (`gnd_benchmark_v1` by default), a
non-empty duplicate-free tuple of `method_execution_ids`, and an optional `aggregation_execution_id`. Like
aggregation, the command resolves the definition, atomically persists a `queued` `EvaluationExecution` and
its CPU-queue outbox intent, and returns `202 Accepted` without computing anything in the request.

`GET /api/v1/evaluations/{evaluation_id}` reads lifecycle state.
`GET /api/v1/evaluations/{evaluation_id}/report` streams the completed report artifact's bytes under the
media type recorded on the artifact; an evaluation without a report artifact returns `404`. See
[ADR-0027](decisions/ADR-0027-gnd-benchmark-evaluation-definition.md).

### Export

`POST /api/v1/exports`

`ExportCreateRequest` selects a `run_id` and a completed `aggregation_execution_id`, a `format` (`tei`,
`json`, or `csv`), a `label_source_policy` (`machine_aggregation` by default, or `human_overrides`), an
optional `tei_profile` valid only when `format` is `tei`, and a `human_resp_id` defaulting to `#editor`.
The command persists a `queued` `ExportExecution` and its CPU-queue outbox intent, and returns
`202 Accepted`.

`GET /api/v1/exports/{export_id}` reads lifecycle state, and
`GET /api/v1/exports/{export_id}/download` returns the primary output bytes resolved through the artifact
record. Downloads use export IDs and artifact references, never server paths.

### Synchronous name classification

`POST /api/v1/classify`

Classifies one or more raw name strings synchronously across registered or specified method adapters. Returns the canonical label, status, method-specific confidence, and raw label for each method, as well as an ensemble `aggregated` verdict with certainty rating (`certainty_tier`), agreement rating (`agreement_tier`, `agreement_score`), vote counts, and priority override source.

Input payload:
- `names`: list of non-blank names (a single `name` string is coerced to a one-element list), bounded to 1,000 names;
- `methods`: optional subset of registered method identifiers (defaults to all runnable methods);
- `method_configs`: optional per-method configuration overrides.

An unknown method identifier fails with `422` and code `validation_error`. This is the one synchronous
scientific endpoint; see
[ADR-0028](decisions/ADR-0028-synchronous-on-demand-classification-api.md).

## List endpoints

Potentially large or changing collections use cursor pagination. `limit` is bounded to `1..200` and
defaults to `100`, and `cursor` is bounded to 2,048 characters. Every paginated collection except
`review-items` takes `limit` and `cursor` only and traverses one stable server-side order:

| Collection | Order |
|---|---|
| `/api/v1/projects` | project slug |
| `/api/v1/projects/{project_id}/snapshots` | newest first |
| `/api/v1/snapshots/{snapshot_id}/people` | TEI `xml:id` |
| `/api/v1/snapshots/{snapshot_id}/runs` | newest first |
| `/api/v1/runs/{run_id}/aggregations` | newest first |
| `/api/v1/runs/{run_id}/evaluations` | newest first |
| `/api/v1/runs/{run_id}/exports` | newest first |
| `/api/v1/aggregations/{aggregation_id}/results` | person record ID |

Newest first means descending `created_at`, with the resource ID breaking ties between resources created in
one transaction. These collections list every resource under their parent in any lifecycle state, so a
client can find a pending import or a failed run again after a reload. They are the only way to discover the
identifiers the resource paths need, since every other route addresses one resource by ID. Only
`/api/v1/review-items` carries filters and a sort selector.

Representative query:

```text
GET /api/v1/snapshots/{snapshot_id}/people
    ?limit=100
    &cursor=...
```

`CursorPage` in [`gendertagger.models.api`](../src/gendertagger/models/api.py) is the shared page contract:

```python
class CursorPage(BaseModel, Generic[T]):
    """Opaque-cursor page for a stable server-ordered resource collection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[T]
    next_cursor: str | None = Field(default=None, min_length=1)
    has_more: bool
```

A model validator rejects any page whose `has_more` and `next_cursor` disagree, so a client never sees a
truthy `has_more` without a cursor to follow. The cursor itself is opaque and keyset-based: it encodes the
resource scope, the last row's sort values, and the last row's ID, never an offset.

No list response carries a total count. Calculating one would make ordinary navigation expensive, and
absent counts keep the contract honest while a snapshot is still being reviewed. Counts that a screen needs
come from a separate resource instead: the [review summary](#review-summary) counts one aggregation's results
in a single grouped read.

Filtering, search, and sorting are performed server-side. `ReviewItemQuery` in
[`gendertagger.models.review`](../src/gendertagger/models/review.py) defines the review-oriented filters:

| Field | Meaning |
|---|---|
| `aggregation_id` | Required; scopes the query to one completed aggregation |
| `final_label` | Canonical label after human override |
| `certainty_tiers` | Any of these reference certainty tiers of the aggregated result |
| `agreement_tiers` | Any of these categorical agreement tiers among answering methods |
| `workflow_states` | Any of `unreviewed`, `reviewed`, and `deferred` |
| `has_authority_conflict` | Authority-vs-ensemble disagreement |
| `method_name` | Selects the method projected as `selected_method_result` |
| `method_label` | Label of that method; requires `method_name` |
| `prediction_status` | `success`, `abstain`, or `error` for that method; requires `method_name` |
| `has_prediction_error` | Any selected method failed technically |
| `q` | Text search over `tei_id`, surname, forenames, alternate names, and external IDs |
| `sort` | `uncertainty` (default) or `tei_id` |
| `limit`, `cursor` | Pagination controls |

The three plural filters are repeated query parameters. A result matches when its value is any of the listed
values, an absent parameter matches every value, and a repeated value is a `422` validation error. The
server keeps the values in vocabulary order, so a cursor stays valid whichever order the client lists them
in. The two review queues of decision D2 in [`24-frontend-delivery-plan.md`](24-frontend-delivery-plan.md)
are therefore one query each: contested evidence is `certainty_tiers=low&certainty_tiers=contested`, and thin
evidence is `certainty_tiers=single&certainty_tiers=uncertain`.

List responses include enough summary data to render a table or card list without one detail request per row. Large raw outputs stay on detail endpoints.

## Review items

A dedicated `review-items` resource is allowed because review triage is a domain concept. It should project the relevant person, final/aggregated result, disagreement/certainty information, and current review revision into a queryable summary.

```text
GET /api/v1/review-items
    ?aggregation_id=...
    &sort=uncertainty
    &certainty_tiers=low
    &certainty_tiers=contested
    &workflow_states=unreviewed
    &limit=100
    &cursor=...
```

`sort` selects `uncertainty` (the default, applying the versioned `review_triage_v1` rank) or `tei_id`. The sort key is immutable for a completed aggregation, so a concurrent annotation never moves a record between pages; see [annotation and review](09-annotation-and-review.md) and [ADR-0022](decisions/ADR-0022-uncertainty-first-review-ordering.md). A cursor is scoped to both the filters and the sort, so reusing it under a different query returns `422` with `invalid_cursor`.

### Review summary

`GET /api/v1/aggregations/{aggregation_id}/review-summary` counts one completed aggregation's results by
certainty tier, agreement tier, and current review state. It returns a `ReviewSummary`: the aggregation ID,
the total `result_count`, and one `ReviewSummaryGroup` for every combination that has results, each with its
`result_count`. Groups follow the declaration order of the three vocabularies, a combination without results
is absent, and the group counts add up to the total.

The summary joins results to review state exactly as the review-item query does, so the count of any
combination of tiers and states equals the number of items the same `certainty_tiers`, `agreement_tiers`, and
`workflow_states` filters return. A client therefore sizes a queue by adding the matching groups, without
paging through it. Certainty and agreement are immutable for a completed aggregation; the review states are
those at read time. An aggregation that is not `completed` returns `409 resource_conflict`, like
`review-items`.

The summary is a projection of the review domain, not a dashboard endpoint: it carries no screen-specific
selection, and each screen composes its figures from the groups.

Avoid page-specific endpoints such as `/getDashboardStuff` or `/getDataForRunPage`.

## Progress/events

Use Server-Sent Events initially for server-to-client progress:

```text
GET /api/v1/runs/{run_id}/events
```

The stream emits six event names:

- `run.state_changed`, carrying `RunStateEvent`;
- `run.progress`, carrying `RunStateEvent`;
- `method_execution.state_changed`, carrying `MethodExecutionStateEvent`;
- `method_execution.progress`, carrying `MethodExecutionStateEvent`;
- `run.completed`, the terminal event on success, carrying `RunStateEvent`;
- `run.failed`, the terminal event on failure, carrying `RunStateEvent`.

Event payloads are Pydantic contracts. Persist authoritative task/run state in PostgreSQL. SSE events are a convenience view, not the only state channel. Clients must be able to reconnect and recover by GETting the current resource state.

`Last-Event-ID`/resume needs persisted, ordered events; it is recorded in [`22-future-development.md`](22-future-development.md).

## Progress model

Expose progress in `Run` and `MethodExecutionSummary` responses. The public execution summary carries
scientific and lifecycle provenance only; queue routing and worker metadata remain internal to
`MethodExecution`.

```python
class Progress(BaseModel):
    total: int | None = Field(default=None, ge=0)
    completed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    percentage: float | None = Field(default=None, ge=0, le=100)
```

`total=None` is valid before work can be counted. Percentage is derived and is not the authoritative completion condition.

## Error model

Define one Pydantic error envelope with:

- stable error code;
- human-readable message;
- optional details;
- correlation/request ID.

Representative body:

```json
{
  "error": {
    "code": "annotation_conflict",
    "message": "The review state has changed.",
    "details": {"current_revision": 5},
    "request_id": "..."
  }
}
```

Normalize framework validation errors into the documented public error shape where practical. Do not expose worker tracebacks to ordinary API users.

## Concurrency

Ordinary immutable resources do not need client-side locking. Annotation/review commands use optimistic concurrency through a monotonically increasing review revision scoped to the person/snapshot decision stream.

Stale writes return `409 Conflict` with code `annotation_conflict`. This protects multi-user review without mutating append-only annotation history.

## Authentication surface

Expose `/api/v1/me` using a typed `CurrentUser` contract. Authorization belongs in FastAPI dependencies/application services, never only in the Vue UI.

For the same-origin browser application, secure HTTP-only session cookies plus CSRF protection cover state-changing requests. The local account provider ([ADR-0031](decisions/ADR-0031-local-database-authentication.md), with session lifetimes from [ADR-0032](decisions/ADR-0032-sliding-session-lifetime.md)) supplies them:

- `POST /auth/login` takes a `LoginRequest` (`username`, `password`, and `keep_signed_in`, default `false`), returns `CurrentUser`, and sets two cookies: `session`, which is `HttpOnly`, and `csrf_token`, which the client reads and mirrors into the `X-CSRF-Token` header on unsafe requests. A failed login is a generic `401 invalid_credentials`. Behind the gateway, repeated attempts from one address receive `429 rate_limited` with a `Retry-After` header; the gateway, not the API, issues it, in the same error envelope.
- Without `keep_signed_in`, both cookies are browser-session cookies and the session ends after 24 hours without a request. With it, both cookies persist until the session's absolute limit and the idle limit is 7 days. Every session ends 30 days after login at the latest. Each request slides the idle limit forward, so an active user is not signed out before the absolute limit.
- `GET /auth/session` returns `CurrentSession` (`must_change_password`, `keep_signed_in`), so the client can learn about a forced password change right after login or on page load.
- `POST /auth/logout` revokes the current session and clears both cookies.
- `POST /me/password` takes a `ChangePasswordRequest` (`current_password`, `new_password`, at least 12 characters) and clears the forced-change flag. A wrong current password is `400 invalid_current_password`, never `401`: a `401` always means that no valid session exists.

Account provisioning is CLI-only (`gendertagger users create` / `reset-password`); there is no HTTP surface for it. A separate token/OIDC mechanism for external machine clients is recorded in [`22-future-development.md`](22-future-development.md).

## CORS

Production should prefer a single origin for Vue and FastAPI, making general CORS unnecessary.

Development may explicitly allow the Vite origin (for example `http://localhost:5173`). Never use wildcard origins with credentialed requests.

## OpenAPI

Treat generated OpenAPI as part of the public contract.

A committed OpenAPI snapshot test detects unintended schema changes: `tests/fixtures/openapi-v1.json` must equal the live schema. `scripts/update_openapi_snapshot.py` owns the one rendering of that snapshot; it rewrites the file, and the contract test runs it with `--check`. The frontend generates its TypeScript transport types from that snapshot, and the `frontend_quality` CI job (`npm run api:check`) fails when the committed `frontend/src/api/schema.d.ts` is stale, so a contract change must also regenerate the client with `npm --prefix frontend run api:generate`. Do not maintain duplicate handwritten transport models.

See `17-frontend-integration.md` and `decisions/ADR-0006-vue-browser-client-boundary.md`.
