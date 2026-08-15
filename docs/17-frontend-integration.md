# Frontend integration and browser-client contract

## Decision

The planned browser UI is **Vue 3 + TypeScript + Vite**. It is a client of the public FastAPI API, not a privileged application layer and not a second source of truth.

The backend must remain fully usable without the frontend by CLI, tests, external integrations, and future clients.

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
      |
      +--> PostgreSQL
      +--> Celery/Redis
      +--> artifact storage
```

The browser must never depend on:

- SQLAlchemy models or database table shapes;
- Celery task IDs, worker hostnames, Redis keys, or queue names;
- filesystem paths;
- Python implementation details;
- classifier-specific internal APIs.

Infrastructure details may be exposed through a separate protected diagnostics/admin surface if operationally useful, but are not part of the ordinary client contract.

## OpenAPI and TypeScript

FastAPI's generated OpenAPI document is the canonical machine-readable frontend contract.

When the Vue application is introduced:

1. generate TypeScript API types/client code from OpenAPI;
2. do not hand-maintain duplicate Python and TypeScript schema definitions;
3. regenerate the client in CI and fail on unexpected contract drift;
4. commit generated client code only if that proves more practical for the team's workflow; otherwise generate it during build.

The generated client is transport code only. UI-specific view models may wrap it, but must not redefine scientific semantics.

## JSON conventions

Public `/api/v1` JSON uses stable, explicit conventions:

- field names: `snake_case`;
- enums: stable lowercase string values;
- identifiers: UUID strings except canonical TEI `xml:id` values;
- timestamps: timezone-aware ISO 8601 UTC values;
- absent optional values: `null`, not magic strings;
- scientific `unknown` is represented only by the canonical label and never conflated with `null`;
- API errors use the shared error envelope from `05-api.md`.

Changing public field names or enum values is an API change even if the Python model name changes cleanly.

## Long-running operations

Imports, runs, method executions, evaluations, and exports are asynchronous resources.

The browser must never keep an HTTP request open for the duration of a classifier run.

Representative flow:

```text
POST /api/v1/runs
  -> 202 Accepted
  -> Run(status="queued")

GET /api/v1/runs/{run_id}
  -> current persisted state

GET /api/v1/runs/{run_id}/events
  -> optional SSE progress/events
```

The resource ID, not a Celery task ID, is the stable handle returned to clients.

## Progress and Server-Sent Events

Use SSE for server-to-client progress until a genuine bidirectional realtime requirement appears.

SSE events use a typed Pydantic payload and stable event names. `GET /api/v1/runs/{run_id}/events`
([`api/run_events.py`](../src/gendertagger/api/run_events.py)) emits six:

- `run.state_changed` and `run.progress`, carrying `RunStateEvent`
- `method_execution.state_changed` and `method_execution.progress`, carrying
  `MethodExecutionStateEvent`
- `run.completed` or `run.failed` as the terminal event, carrying `RunStateEvent`

Authoritative state remains in PostgreSQL. Losing an SSE connection must not lose scientific or workflow state.

The UI must always be able to reconnect and refresh the current resource state through normal GET endpoints. No event log is retained, so the stream projects current state rather than replaying history; `Last-Event-ID` resume is recorded in [`22-future-development.md`](22-future-development.md).

Reverse-proxy configuration must disable response buffering for SSE routes and permit sufficiently long-lived HTTP connections.

## Progress contracts

Both Run and MethodExecution summaries expose progress through the shared `Progress` contract in
[`models/run.py`](../src/gendertagger/models/run.py):

```python
class Progress(BaseModel):
    total: int | None = Field(default=None, ge=0)
    completed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    percentage: float | None = Field(default=None, ge=0, le=100)
```

`total=None` is valid when the total is not known yet. `Progress.of` derives the percentage from the
counts; percentage is derived and must not be used as the authoritative completion condition.

## Lists, search, filtering, and sorting

Large collections are queried on the server. The Vue application must not fetch all people/predictions and reproduce database filtering in browser state.

Use cursor pagination by default for potentially large or changing collections:

```text
GET /api/v1/snapshots/{snapshot_id}/people
    ?limit=100
    &cursor=...
    &q=Johann
    &sort=tei_id
```

Review-oriented queries should expose domain filters such as:

- canonical/final label;
- certainty tier;
- agreement tier;
- reviewed/unreviewed/deferred state;
- authority-vs-ensemble conflict;
- selected method result;
- prediction status/error presence;
- free-text name search.

A dedicated `review-items` resource is acceptable because review triage is a domain concept. Avoid page-specific endpoints such as `getDashboardStuff`.

Review triage ordering is also a server concern. `GET /api/v1/review-items` defaults to `sort=uncertainty` and additionally accepts `sort=tei_id`; the Vue application must not re-rank a page in browser state. Keep the returned cursor with the query that produced it, because a cursor is scoped to both the filters and the sort.

List responses should contain summaries sufficient to render the list without one follow-up request per row. Details and full raw method output belong on detail endpoints.

## Annotation concurrency

Annotations remain immutable, append-only scholarly decisions.

For concurrent review, maintain a monotonically increasing **review revision** for the person/snapshot decision stream. A create/correction command includes the revision observed by the client:

```python
class AnnotationCreate(BaseModel):
    snapshot_id: UUID
    tei_id: str
    action: ReviewAction
    label: CanonicalLabel | None = None
    comment: str | None = None
    aggregated_result_id: UUID | None = None
    expected_revision: int = Field(ge=0)
```

If another reviewer has changed the stream since that revision, return:

```text
409 Conflict
error.code = "annotation_conflict"
```

The client then reloads the current review state and lets the reviewer decide again. Never silently overwrite another annotation and never mutate the historical annotation row.

The domain revision is authoritative. Mirroring it into ETag/`If-Match` headers is recorded in
[`22-future-development.md`](22-future-development.md).

## Authentication for the browser

The browser deployment uses secure, HTTP-only session cookies rather than storing long-lived bearer tokens in JavaScript-accessible storage.

CSRF protection is enforced for state-changing browser requests: the `/api/v1` router carries the `require_csrf_protection` dependency, so every unsafe method is validated against its browser session.

The backend exposes a typed `CurrentUser`/`/api/v1/me` contract. Application services authorize actions from that identity; the UI merely hides/disables controls for convenience.

A separate token/OIDC flow for external machine clients is recorded in
[`22-future-development.md`](22-future-development.md).

## Same-origin deployment

Preferred production topology:

```text
https://gendertagger.example.org/
    /                 -> Vue static assets
    /api/v1/...       -> FastAPI
```

The reverse proxy owns TLS and routing. Same-origin deployment avoids unnecessary production CORS complexity and simplifies secure cookie authentication.

Development topology may use:

```text
http://localhost:5173  -> Vite
http://localhost:8000  -> FastAPI
```

FastAPI may allow an explicit development origin. Never use wildcard CORS together with credentials.

## Frontend state management

When the Vue UI is implemented:

- use generated OpenAPI client/types for transport;
- treat server resources as server state, preferably through a query/cache library rather than copying everything into global state;
- use Pinia only for genuinely shared client/UI state;
- keep scientific normalization, aggregation, permission checks, and final-decision logic on the backend;
- optimistic UI is acceptable only where it cannot obscure a failed scholarly write.

No frontend library choice beyond Vue 3 + TypeScript + Vite is normative yet.

## Upload and download boundary

The browser uploads source material and downloads generated artifacts through API resources. It never receives or supplies server filesystem paths.

Examples:

```text
POST /api/v1/projects/{project_id}/snapshots
POST /api/v1/exports
GET  /api/v1/exports/{export_id}
GET  /api/v1/exports/{export_id}/download
```

Signed-URL delivery for very large artifacts is recorded in
[`22-future-development.md`](22-future-development.md).

## Completed backend capabilities

Every backend prerequisite for frontend implementation is delivered:

- stable `/api/v1` routing;
- explicit Pydantic request and response models;
- OpenAPI contract tests;
- shared error envelope;
- cursor-pagination conventions;
- server-side filtering/search/sorting;
- async `202 Accepted` resource creation for long operations;
- Run and MethodExecution progress contracts;
- reconnect-safe SSE convenience stream;
- append-only annotation commands with optimistic concurrency;
- explicit `CurrentUser` contract;
- browser-safe session/CSRF design;
- same-origin production topology;
- upload/download via artifacts rather than paths.

`frontend/` itself is still a placeholder. Scaffolding Vue 3 + TypeScript + Vite, generating the
transport client, and building the review interface are the remaining Phase 8 items in
[`15-implementation-plan.md`](15-implementation-plan.md).
