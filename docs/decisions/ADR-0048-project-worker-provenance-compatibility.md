# ADR-0048: Project worker provenance compatibility

**Status:** Accepted

## Context

Project classification batches currently select the worker's registered adapter without comparing it
with the immutable MethodExecution versions or accepted Run environment. A deployment between acceptance
and execution can therefore attribute new method outputs to old provenance. Public classification already
rejects changed method/environment identities under [ADR-0044](ADR-0044-public-name-classification.md).
The [task specification](../06-task-queue.md) and [provenance specification](../11-provenance-and-reproducibility.md)
require equivalent protection for project work, without putting datasets into task envelopes.

## Decision

1. Capture exact installed dependency versions when accepting a new Run, alongside its existing source
   revision, application/Python versions, dependency-lock digest, and optional image digest. Persist the
   dependency map as immutable Run provenance. Existing runs retain a null map; do not invent historical
   environment evidence.
2. Before calling an adapter, require its implementation and normalization versions to equal the persisted
   MethodExecution versions. Require the worker's source, application, Python, lock, installed dependency,
   and image identities to equal the Run's accepted identities. Missing accepted dependency evidence is
   incompatible, not an invitation to substitute the current environment.
3. Validate the exact persisted configuration and its canonical digest. Where assets are applicable, use
   the accepted artifact digest, never the latest artifact or worker defaults. Verify lookup/manifest bytes,
   manifest method identity, and model members before prediction, including the materialized model files
   actually passed to adapters. Operator-declared external LLM aliases/revisions remain declarations rather
   than independent attestation of a remote server's weights.
4. Capture actual worker identity through a frozen, closed Pydantic `WorkerProvenance`: source/application/
   Python/lock/dependency/image identity plus hostname and process ID. Persist it with the atomic TaskBatch
   claim. It is operational provenance at claim time, then immutable; terminal and duplicate delivery cannot
   replace it. Keep MethodExecution's already sealed metadata unchanged. Transient rollback also rolls back
   the claim and receipt; the eventual terminal batch identifies its completing worker, not a new attempt log.
5. Incompatibility is a permanent, persisted `IncompatibleWorkerError` batch failure with a bounded,
   sanitized diagnostic and no Prediction rows. Existing execution/run failure propagation remains intact.
   Redelivery is a terminal no-op, even if a compatible worker later receives the message.
6. Recover by finishing unclaimed work in its matching recorded environment, or by accepting a new Run under
   the desired environment. After a batch has failed, do not reopen it or rewrite accepted provenance,
   predictions, historical runs, or previous outputs. Pre-cutover runs without dependency evidence must be
   newly accepted to execute under the guarded worker.

A reviewed migration adds nullable historical Run dependency and TaskBatch worker-provenance fields,
protects Run identity under the existing provenance guard, and permits batch receipt creation only during
claim. Run's public read schema gains the dependency map; regenerate OpenAPI and frontend transport types.
Worker hostname/process identity stays internal. Task messages still contain only execution and batch IDs.

## Consequences

Compatible work follows the existing immutable-output and retry policy. Deployments cannot silently mix
accepted v1 method/environment metadata with v2 output. Strong asset verification adds file I/O before
scientific computation; it is preferred to attributing altered model or lookup bytes to a pinned artifact.
No scientific labels, normalization, aggregation, golden expectations, or historical evidence change.

Regression coverage must exercise implementation/normalization and every environment identity boundary,
asset/model drift, compatible execution, missing historical evidence, transient retry, duplicate delivery,
and database rejection of receipt/provenance rewrites. Runtime proof must execute the service against real
PostgreSQL and exercise the existing Redis worker composition rather than relying only on test doubles.
