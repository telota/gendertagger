# Deployment and operations

## Initial deployment

Use Docker Compose. Keep the service topology boring and inspectable.

```text
reverse-proxy
  -> `/` Vue static frontend
  -> `/api/v1` FastAPI

api
  -> postgres
  -> redis
  -> shared artifact storage

workers
  -> postgres
  -> redis
  -> shared artifact storage
  -> local model/data volumes
```

## Data locality

The default architecture supports an entirely local/private deployment. The reference pipeline's LLM is local, and GND should be consumed from a local snapshot rather than queried live during classification.

Future external methods must be explicitly configured and visibly marked because sending historical register content outside the editorial environment can be unacceptable for licensing/privacy/policy reasons.

## Health endpoints

FastAPI:

- `/health`: process alive
- `/ready`: dependencies sufficiently available to serve requests

Worker health should be observable separately.

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
