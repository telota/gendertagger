# FastAPI design

## Principles

FastAPI is the canonical public interface. The browser UI, CLI where remote operation is desired, and external edition integrations consume the same application semantics.

Version the public API under `/api/v1`.

Favor resource-oriented endpoints over classifier-specific or page-specific RPC endpoints. A Vue screen is not an API resource; a Run, ReviewItem, Annotation, Export, or Evaluation is.

The API exposes explicit Pydantic request/response models and never SQLAlchemy instances. OpenAPI is a public machine-readable contract and should be used to generate TypeScript transport types/client code for the future Vue application.

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

```text
/api/v1/projects
/api/v1/projects/{project_id}
/api/v1/projects/{project_id}/snapshots
/api/v1/snapshots/{snapshot_id}
/api/v1/snapshots/{snapshot_id}/people
/api/v1/review-items
/api/v1/runs
/api/v1/runs/{run_id}
/api/v1/runs/{run_id}/executions
/api/v1/runs/{run_id}/predictions
/api/v1/runs/{run_id}/aggregations
/api/v1/runs/{run_id}/events
/api/v1/aggregations/{aggregation_id}/results
/api/v1/annotations
/api/v1/evaluations
/api/v1/exports
/api/v1/exports/{export_id}/download
/api/v1/methods
/api/v1/classify
/api/v1/me
```

## Long-running commands

Imports, runs, method execution, aggregation, evaluations, and exports are asynchronous resources. Do not keep
an HTTP request open while scientific computation executes.

Representative flow:

```text
POST /api/v1/runs
  -> 202 Accepted
  -> Run(id=..., status="queued")

GET /api/v1/runs/{run_id}
  -> persisted current state
```

Return domain resource IDs, never Celery task IDs. Celery is an internal execution mechanism and can change without changing the public API.

Accepting an asynchronous command atomically persists its domain resource and one typed outbox intent in
PostgreSQL. A dispatch owns exactly one task batch, aggregation execution, or dataset snapshot and carries only
its small validated identifier envelope. The FastAPI process does not publish those messages to Redis. A
`202 Accepted` response therefore confirms durable application state and dispatch intent, not immediate broker
delivery; the dispatch coordinator relays and reconciles that intent asynchronously.

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

Input:

- `dataset_snapshot_id`;
- run configuration or named server-side config.

Result: persisted Run with resolved config hash and queued/runnable state.

### Start/run executions

Prefer explicit state transitions or a create-run option rather than method-named endpoints. For example:

`POST /api/v1/runs/{run_id}/executions`

This command returns the persisted run after the scheduling transaction commits. Broker outages do not turn
an otherwise successful durable scheduling command into an HTTP failure.

### Aggregate

`POST /api/v1/runs/{run_id}/aggregations`

Aggregation must be independently rerunnable without classifier execution. The command selects the exact
completed MethodExecutions, then atomically creates a `queued` `AggregationExecution` and its CPU-queue outbox
intent. It returns that resource with `202 Accepted`, never a Celery task ID, and does not compute results in
the request.

Clients read lifecycle state through:

```text
GET /api/v1/aggregations/{aggregation_id}
```

Only `status=completed` guarantees that the results collection contains exactly one immutable result for every
person in the run snapshot. `status=failed` includes a sanitized diagnostic and exposes no partial result set.
Broker downtime leaves the resource safely queued for the coordinator. See
[ADR-0016](decisions/ADR-0016-asynchronous-aggregation-outbox.md).

### Annotate

`POST /api/v1/annotations`

Creates a new immutable human decision. The command contains the review revision observed by the client. A stale revision returns `409 Conflict`; no historical annotation is overwritten.

### Export

`POST /api/v1/exports`

Creates an asynchronous export resource referencing a snapshot plus selected aggregation/final-decision policy. Downloads use artifact/export IDs, never server paths.

### Synchronous name classification

`POST /api/v1/classify`

Classifies one or more raw name strings synchronously across registered or specified method adapters. Returns the canonical label, status, method-specific confidence, and raw label for each method, as well as an ensemble `aggregated` verdict with certainty rating (`certainty_tier`), agreement rating (`agreement_tier`, `agreement_score`), vote counts, and priority override source.

Input payload:
- `names`: list of non-blank names (or a single `name` string, bounded to 1,000 names);
- `methods`: optional subset of registered method identifiers (defaults to all runnable methods);
- `method_configs`: optional per-method configuration overrides.

## List endpoints

Potentially large or changing collections use cursor pagination by default.

Representative query:

```text
GET /api/v1/snapshots/{snapshot_id}/people
    ?limit=100
    &cursor=...
    &q=Johann
    &sort=tei_id
```

A shared cursor page contract should contain at least:

```python
T = TypeVar("T")


class CursorPage(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None
    has_more: bool
```

Do not expose total counts by default when calculating them would make ordinary navigation expensive. Endpoints that can provide a cheap/meaningful count may add it explicitly.

Filtering/search/sorting is performed server-side. Review-oriented filters should include, where applicable:

- final/canonical label;
- certainty tier;
- agreement tier;
- reviewed/unreviewed/deferred state;
- authority-vs-ensemble disagreement;
- selected method result;
- prediction status/errors;
- text search over names/identifiers.

List responses should include enough summary data to render a table/card list without one detail request per row. Keep large raw outputs on detail endpoints.

## Review items

A dedicated `review-items` resource is allowed because review triage is a domain concept. It should project the relevant person, final/aggregated result, disagreement/certainty information, and current review revision into a queryable summary.

```text
GET /api/v1/review-items
    ?aggregation_id=...
    &sort=uncertainty
    &certainty_tier=contested
    &limit=100
    &cursor=...
```

`sort` selects `uncertainty` (the default, applying the versioned `review_triage_v1` rank) or `tei_id`. The sort key is immutable for a completed aggregation, so a concurrent annotation never moves a record between pages; see [annotation and review](09-annotation-and-review.md) and [ADR-0022](decisions/ADR-0022-uncertainty-first-review-ordering.md). A cursor is scoped to both the filters and the sort, so reusing it under a different query returns `422` with `invalid_cursor`.

Avoid page-specific endpoints such as `/getDashboardStuff` or `/getDataForRunPage`.

## Progress/events

Use Server-Sent Events initially for server-to-client progress:

```text
GET /api/v1/runs/{run_id}/events
```

Suggested stable event names:

- `run.state_changed`;
- `run.progress`;
- `method_execution.state_changed`;
- `method_execution.progress`;
- `aggregation.state_changed`;
- `aggregation.completed`;
- `aggregation.failed`;
- `run.completed`;
- `run.failed`.

Event payloads are Pydantic contracts. Persist authoritative task/run state in PostgreSQL. SSE events are a convenience view, not the only state channel. Clients must be able to reconnect and recover by GETting the current resource state.

Support `Last-Event-ID`/resume when event persistence exists; it is not required for the first asynchronous slice.

## Progress model

Expose progress in `Run` and `MethodExecutionSummary` responses. The public execution summary carries
scientific and lifecycle provenance only; queue routing and worker metadata remain internal to
`MethodExecution`.

```python
class Progress(BaseModel):
    total: int | None
    completed: int
    failed: int
    percentage: float | None
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

For the same-origin browser application, prefer secure HTTP-only session cookies plus CSRF protection for state-changing requests. External machine clients may later use a separate token/OIDC mechanism.

## CORS

Production should prefer a single origin for Vue and FastAPI, making general CORS unnecessary.

Development may explicitly allow the Vite origin (for example `http://localhost:5173`). Never use wildcard origins with credentialed requests.

## OpenAPI

Treat generated OpenAPI as part of the public contract.

Tests/CI should detect unintended schema changes. When the Vue frontend exists, its generated TypeScript client/types should be regenerated or checked from this schema. Do not maintain duplicate handwritten transport models.

See `17-frontend-integration.md` and `decisions/ADR-0006-vue-browser-client-boundary.md`.
