# ADR-0028: Synchronous on-demand name classification API

**Status:** Accepted

## Context

GenderTagger's primary scientific workflow processes historical person registers through immutable TEI dataset snapshots, asynchronous Celery task batches, outbox dispatches, and reproducible voting aggregations (see [`01-architecture.md`](../01-architecture.md), [`05-api.md`](../05-api.md), and [`06-task-queue.md`](../06-task-queue.md)).

While that architecture is essential for large-scale, reproducible corpus runs, interactive consumers — such as browser exploration tools, single-name lookup widgets, and external edition integrations — require immediate, synchronous classification of raw name strings without creating a persistent project, uploading a TEI snapshot, or dispatching asynchronous background tasks.

The system needs a lightweight, direct HTTP classification interface that evaluates one or more names across all or a selected subset of registered method adapters while strictly upholding canonical contracts, Pydantic validation, and method-level error isolation.

## Decision

Introduce the synchronous classification endpoint `POST /api/v1/classify` backed by `DirectClassificationService`:

1. **Endpoint & Authorization**:
   - Exposed as `POST /api/v1/classify` within the versioned `/api/v1` router.
   - Protected by standard CSRF validation and requiring viewer capability (`require_viewer`).

2. **Request Contract**:
   - `ClassifyNamesRequest` in `gendertagger.models.classify` accepts:
     - `names`: one or more non-blank name strings, bounded to a maximum of 1,000 names per synchronous request to prevent HTTP timeouts. Input coercion seamlessly normalizes single-string inputs (e.g. `{"name": "Maria"}` or `{"names": "Maria"}`) into `names: list[str]`.
     - `methods`: an optional sequence of registered lowercase snake-case method identifiers. When omitted, all registered runnable methods on the server are executed. Unknown method names are rejected with validation error `422`.
     - `method_configs`: optional per-method configuration dictionaries for parameter overrides (e.g., custom probability thresholds).

3. **Response Contract**:
   - `ClassifyNamesResponse` contains `results: list[NameClassificationResult]`, preserving the requested name order.
   - Each `NameClassificationResult` contains the input `name` string, `classifications: dict[str, MethodClassification]` mapping each method name to its classification outcome, and `aggregated: AggregatedClassification`:
     - Method classifications provide: `label`, `status`, `method_confidence`, `raw_label`, and `error_message`.
     - `AggregatedClassification` provides: `label` (consensus label), `outcome` (`decided`, `unresolved_tie`, `no_data`), `certainty_tier` (`high`, `medium`, `low` when reference suite is evaluated per [ADR-0009](ADR-0009-reference-agreement-certainty.md)), `agreement_tier`, `agreement_score`, `vote_counts`, and `override_source` (`parenthetical_qualifier` or `gnd` if priority override applied).

4. **Service Execution, Caching & Error Isolation**:
   - `DirectClassificationService` in `gendertagger.services.classification` maps name strings into synthetic `PersonInput` models (`forenames=[name]`).
   - An in-memory, thread-safe LRU cache (bounded to 50,000 entries) caches classification predictions per `(method, config, name)`, avoiding redundant execution for repeated names.
   - For methods requiring content-addressed SQLite lookups or model directories, configuration automatically resolves the latest registered artifact of the required logical type from the artifact repository when no explicit digest is supplied.
   - Execution of each method adapter is isolated with structured error handling: runtime dependency errors (`MethodDependencyError`) or missing lookup assets mark that individual method's result as `status: "error"` with an informative diagnostic message, allowing all other enabled methods to run and return valid results without failing the HTTP request.
   - Ensemble assessment automatically applies reference aggregation rules ([ADR-0003](ADR-0003-reference-aggregation.md), [ADR-0008](ADR-0008-reference-aggregation-edge-contract.md), [ADR-0009](ADR-0009-reference-agreement-certainty.md)) across method predictions.

## Consequences

- Clients and interactive UI tools can query the classification ensemble on demand for individual names or small batches with minimal latency, instant LRU cache reuse, and zero database or Celery outbox overhead.
- Responses include both detailed per-method audit evidence and the unified ensemble consensus with certainty ratings.
- All per-method normalization profiles, token filtering, and method descriptors are reused directly from the canonical method adapters without code duplication.
- The 1,000-name batch boundary ensures predictable memory usage and latency on synchronous worker threads.
- Comprehensive OpenAPI schema generation and contract tests reflect the public `/api/v1/classify` interface for frontend client generation.
