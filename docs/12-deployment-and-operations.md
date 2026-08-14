# Deployment and operations

## Initial deployment

Use Docker Compose. Keep the service topology boring and inspectable.

```text
reverse-proxy
  -> `/` Vue static frontend
  -> `/api/v1` FastAPI

api
  -> postgres
  -> shared artifact storage

dispatch-coordinator
  -> postgres
  -> redis

workers
  -> postgres
  -> redis
  -> shared artifact storage
  -> local model/data volumes
```

The API durably stages bounded snapshot uploads in shared artifact storage, then commits snapshot, task-batch,
or aggregation work and its typed dispatch intent to PostgreSQL; it does not publish to Redis. A distinct
dispatch-coordinator process runs the fast generic outbox relay and slower dispatch reconciler. This process is
not a Celery task, because it must remain able to retry durable intent while the broker is unavailable.

## Process topology and startup

API, dispatch coordinator, and ordinary Celery workers use the same backend package and container image with
different startup commands:

| Service | Representative command | Responsibility |
|---|---|---|
| API | `uvicorn gendertagger.api.app:create_app --factory` | HTTP composition and persisted resources |
| Dispatch coordinator | `python -m gendertagger.tasks.relay` | Outbox relay and reconciliation |
| CPU worker | `celery -A gendertagger.tasks.celery_app worker -Q default,cpu` | Snapshot imports, CPU method batches, and aggregation |
| LLM worker | `celery -A gendertagger.tasks.celery_app worker -Q llm` | Isolated local LLM work |

A GPU image may extend the backend image with accelerator dependencies, but it runs the same application
worker entry point. Queue-specific processes can scale and restart independently without changing the API
contract.

Aggregation does not add a service, image, queue class, or public port. The API creates its persisted resource,
the existing coordinator relays its identifier-only message, and an existing CPU worker executes it. This is
the same topology used for method batches with a different typed outbox owner and Celery task name.

Snapshot import uses that topology as well. The API finishes source staging before it accepts the command,
then returns the pending DatasetSnapshot without parsing. The coordinator relays only its snapshot ID and an
existing CPU worker opens the exact artifact from shared storage. In multi-process or container deployments,
configure every API and CPU-worker process with the same absolute `GENDERTAGGER_ARTIFACT_ROOT`, backed by the
same mounted immutable artifact namespace. The relative `data/artifacts` default is suitable only when every
process has an identical working directory and storage mount. Request-local temporary storage is never a
worker input.

Deployment runs `alembic upgrade head` as a one-shot migration step before starting the long-running
processes. After PostgreSQL is ready, API and coordinator may start independently of Redis readiness. When
Redis is unavailable, the API can continue accepting valid method and aggregation commands because dispatch
intent is durable. It can likewise accept a snapshot after its source and outbox intent are durable; the
coordinator retries publication and workers resume consumption after Redis recovers.

Before the first asynchronous-import deployment, stop the old API and inspect snapshots already committed as
`importing`. They may contain partial batches from the former synchronous workflow and are deliberately not
auto-reclaimed. Treat them as interrupted legacy imports and create a new snapshot from their preserved source
after recording the operational disposition; new transactional workers leave failed attempts `pending`
instead of committing that state.

Set `GENDERTAGGER_DISPATCH_PUBLISHED_STALE_SECONDS` above the deployment's normal worst-case queue latency.
The default is 600 seconds. A shorter threshold, or an extended worker outage, intentionally causes duplicate
publication of still-queued targets; atomic task-batch, aggregation, and pending-snapshot claims keep execution
correct, but unnecessary duplicates can amplify a Redis backlog.

For the final Compose deployment, operators start the reverse proxy/frontend, API, dispatch coordinator,
workers, PostgreSQL, Redis, and artifact storage together. The coordinator is an internal service and has no
public port.

## Data locality

The default architecture supports an entirely local/private deployment. The reference pipeline's LLM is local, and GND should be consumed from a local snapshot rather than queried live during classification.

Future external methods must be explicitly configured and visibly marked because sending historical register content outside the editorial environment can be unacceptable for licensing/privacy/policy reasons.

Table-backed method datasets are content-addressed SQLite artifacts, not PostgreSQL lookup tables. Every API
and classification worker must see the same artifact namespace or use a future digest-keyed host-local cache.
Provisioning compiles and publishes lookup artifacts before a run is scheduled; classification opens the
selected artifact read-only and never downloads from DNB, RADAR, Wikipedia, or another external provider.
HIVOTO provisioning remains manual because acquiring its source requires interactive license acceptance.

## Health endpoints

FastAPI:

- `/health`: process alive
- `/ready`: dependencies sufficiently available to serve requests

Worker health should be observable separately.

Dispatch-coordinator health must also be observable separately. Readiness requires PostgreSQL access; Redis
failure should report degraded publication rather than discard or mutate durable dispatch intent. API
readiness does not depend on Redis solely for publication. Accepting a snapshot additionally requires its
configured artifact store; later Redis failure cannot discard the staged source or accepted command.

## Logging

Structured JSON logs with correlation identifiers. Include relevant:

- request_id
- project_id
- snapshot_id
- run_id
- method_execution_id
- batch_id
- aggregation_execution_id

Never rely on logs as the only scientific provenance store.

## Backups

Back up:

- PostgreSQL
- artifact storage
- configuration/secrets required for restoration

Redis does not require scientific backup if all authoritative state is elsewhere.

Test restoration, not merely backup creation.

Content-addressed staging can leave unreferenced blobs when one part or the final database acceptance
transaction fails. Reclaim them only through a reference-aware garbage collector with a grace period; never
delete by age alone while uploads may still be staging or database acceptance may still be in progress.

## Secrets

Secrets are injected through environment/secret management and never stored in repository YAML.

## Resource controls

Configure worker concurrency independently by queue. GPU/LLM workers should default to low concurrency
appropriate to model memory. Reverse-proxy request limits, multipart temporary-storage capacity, and the
application's streamed source limit must agree; the application limit remains authoritative even when an
earlier proxy check is present. CPU-worker memory and temporary capacity must account for bounded XLSX
inspection and archive member streaming as well as database batches.

The API resolves these `GENDERTAGGER_*` settings into each accepted snapshot's immutable import config:

| Setting | Default | Purpose |
|---|---:|---|
| `MAX_TEI_UPLOAD_BYTES` | 100 MiB | Compatibility name for the maximum bytes in each multipart source part |
| `MAX_SNAPSHOT_UPLOAD_BYTES` | 500 MiB | Maximum aggregate uploaded bytes in one snapshot request |
| `MAX_SNAPSHOT_SOURCE_FILES` | 128 | Maximum loose files or archive/workbook members |
| `MAX_ARCHIVE_MEMBER_BYTES` | 100 MiB | Maximum expanded bytes for one archive or workbook member |
| `MAX_ARCHIVE_EXPANDED_BYTES` | 500 MiB | Maximum total expanded bytes for one archive or workbook |
| `MAX_ARCHIVE_COMPRESSION_RATIO` | 100 | Maximum expanded-to-compressed byte ratio |
| `MAX_IMPORT_RECORD_COUNT` | 1,000,000 | Maximum PersonRecords in one snapshot |
| `MAX_TABULAR_CELL_BYTES` | 1 MiB | Maximum bounded size of one tabular cell |
| `TEI_IMPORT_BATCH_RECORD_COUNT` | 500 | Flush group inside the atomic import transaction |

Environment variables use the `GENDERTAGGER_` prefix, for example
`GENDERTAGGER_MAX_ARCHIVE_EXPANDED_BYTES`. Operators should set all limits deliberately for the available API,
artifact-store, worker, and PostgreSQL capacity. A flush group is not a partial commit: the import transaction
still exposes all PersonRecords and `ready` together. Lowering a deployment setting affects future acceptance;
the worker applies the resolved limits persisted with an existing pending snapshot.

Archive and workbook safety does not rely on reverse-proxy limits. Readers independently enforce member count,
expanded sizes, compression ratio, safe regular-member types, and supported content while consuming the
artifact. Before constructing ZIP member objects, they derive a deterministic central-directory metadata cap
as `max(64 KiB, persisted maximum source files × 16 KiB)`; it requires no separate environment setting. XLSX
metadata is securely streamed before the read-only workbook load, so worksheet dimensions and active or
external content fail before workbook materialization. Configure alerts for repeated limit failures because
they may indicate either unsuitable editorial bundles or hostile uploads.

## Metrics

Useful initial operational metrics:

- queue depth
- pending outbox count and oldest pending age
- relay publication latency, attempts, and failures
- expired dispatch leases and reconciliation repairs
- batch duration
- snapshot-import queue latency, duration, retries, and terminal failures
- aggregation queue latency, duration, completion, and failure counts
- aggregation result count versus snapshot person count
- prediction throughput
- success/abstain/error counts
- DB pool saturation
- worker availability
- GPU memory/utilization where available
- export/import duration

Prometheus/Grafana can be added when there is an actual operations environment; they are not prerequisites for the first vertical slice.


## Browser deployment

Prefer same-origin production routing:

```text
https://gendertagger.example.org/           -> Vue static assets
https://gendertagger.example.org/api/v1/... -> FastAPI
```

This reduces CORS/cookie complexity and keeps the browser API boundary explicit. Development may run Vite on `localhost:5173` and FastAPI on `localhost:8000` with an explicit development CORS allow-list.

The reverse proxy must support Server-Sent Events for run progress. Disable proxy response buffering on SSE routes and allow long-lived HTTP connections/keepalives.

The frontend is built/deployed independently of scientific workers. A frontend rebuild must never be required to change queue topology or worker placement.
