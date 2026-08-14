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

The API commits task batches and their dispatch intent to PostgreSQL; it does not publish to Redis. A distinct
dispatch-coordinator process runs the fast outbox relay and slower dispatch reconciler. This process is not a
Celery task, because it must remain able to retry durable intent while the broker is unavailable.

## Process topology and startup

API, dispatch coordinator, and ordinary Celery workers use the same backend package and container image with
different startup commands:

| Service | Representative command | Responsibility |
|---|---|---|
| API | `uvicorn gendertagger.api.app:create_app --factory` | HTTP composition and persisted resources |
| Dispatch coordinator | `python -m gendertagger.tasks.relay` | Outbox relay and reconciliation |
| CPU worker | `celery -A gendertagger.tasks.celery_app worker -Q default,cpu` | CPU batch execution |
| LLM worker | `celery -A gendertagger.tasks.celery_app worker -Q llm` | Isolated local LLM work |

A GPU image may extend the backend image with accelerator dependencies, but it runs the same application
worker entry point. Queue-specific processes can scale and restart independently without changing the API
contract.

Deployment runs `alembic upgrade head` as a one-shot migration step before starting the long-running
processes. After PostgreSQL is ready, API and coordinator may start independently of Redis readiness. When
Redis is unavailable, the API can continue accepting valid scheduling commands because dispatch intent is
durable; the coordinator retries publication and workers resume consumption after Redis recovers.

Set `GENDERTAGGER_DISPATCH_PUBLISHED_STALE_SECONDS` above the deployment's normal worst-case queue latency.
The default is 600 seconds. A shorter threshold, or an extended worker outage, intentionally causes duplicate
publication of still-pending batches; atomic worker claims keep execution correct, but unnecessary duplicates
can amplify a Redis backlog.

For the final Compose deployment, operators start the reverse proxy/frontend, API, dispatch coordinator,
workers, PostgreSQL, Redis, and artifact storage together. The coordinator is an internal service and has no
public port.

## Data locality

The default architecture supports an entirely local/private deployment. The reference pipeline's LLM is local, and GND should be consumed from a local snapshot rather than queried live during classification.

Future external methods must be explicitly configured and visibly marked because sending historical register content outside the editorial environment can be unacceptable for licensing/privacy/policy reasons.

## Health endpoints

FastAPI:

- `/health`: process alive
- `/ready`: dependencies sufficiently available to serve requests

Worker health should be observable separately.

Dispatch-coordinator health must also be observable separately. Readiness requires PostgreSQL access; Redis
failure should report degraded publication rather than discard or mutate durable dispatch intent. API
readiness does not depend on Redis solely for batch publication.

## Logging

Structured JSON logs with correlation identifiers. Include relevant:

- request_id
- project_id
- snapshot_id
- run_id
- method_execution_id
- batch_id

Never rely on logs as the only scientific provenance store.

## Backups

Back up:

- PostgreSQL
- artifact storage
- configuration/secrets required for restoration

Redis does not require scientific backup if all authoritative state is elsewhere.

Test restoration, not merely backup creation.

## Secrets

Secrets are injected through environment/secret management and never stored in repository YAML.

## Resource controls

Configure worker concurrency independently by queue. GPU/LLM workers should default to low concurrency appropriate to model memory.

## Metrics

Useful initial operational metrics:

- queue depth
- pending outbox count and oldest pending age
- relay publication latency, attempts, and failures
- expired dispatch leases and reconciliation repairs
- batch duration
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
