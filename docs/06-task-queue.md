# Task queue and worker design

## Stack

Celery with Redis as broker/result coordination. Durable scientific results are written to PostgreSQL/artifact storage, not Celery result backend.

## Queues

Initial routing classes:

- `default`: lightweight orchestration
- `cpu`: dictionaries, rules, statistical CPU work, parsing, aggregation/evaluation
- `gpu`: Transformer/ML inference that benefits from GPU
- `llm`: locally hosted LLM requests if isolation/concurrency control is useful
- `external`: future rate-limited external services
- `export`: larger export/report jobs if needed

Do not create a queue per method unless operational evidence justifies it.

## Batch model

A MethodExecution is divided into persisted TaskBatches.
Batch sizes are method/resource-specific configuration rather than global constants.

Initial tuning ranges, not normative values:

- CPU lookup/rule work: ~100–500 records per batch
- GPU inference: ~32–256 records per batch depending on model/memory

## Idempotency

Every task must be safe to retry.

Use persisted batch IDs and uniqueness constraints. A retry should upsert/confirm the same scientific result rather than append duplicates.

Method predictions should be committed in bounded batches so a worker failure does not discard thousands of completed classifications.

## Retry policy

Differentiate:

- transient infrastructure failures: retry with exponential backoff and jitter
- validation/scientific input errors: persist as `error`/diagnostic, usually no retry
- LLM schema validation failure: bounded retries according to method config
- permanent model/config errors: fail MethodExecution promptly

## Run completion

A Run may complete with method-level errors. Do not make one failed optional classifier destroy all successfully persisted evidence.

Aggregation can require a configurable minimum set of completed MethodExecutions.
The reference configuration should fail clearly if required published-reference methods are unavailable.

## Cancellation

Cancellation should mark future batches cancelled and revoke queued work where practical. Already persisted Predictions remain as provenance and are not deleted silently.

## Worker observability

Record:

- worker/task IDs
- batch IDs
- queue
- attempts
- start/end times
- counts success/abstain/error
- exception class and sanitized diagnostic

Structured logs should carry `run_id`, `method_execution_id`, and `batch_id` when applicable.
