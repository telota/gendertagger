# ADR-0044: Anonymous bounded name classification

**Status:** Accepted

## Context

External edition integrations need free classification without local accounts, for one name or a batch.
The authenticated on-demand interface in [ADR-0028](ADR-0028-synchronous-on-demand-classification-api.md)
already executes canonical method adapters and aggregation. Opening its arbitrary configuration overrides
would also open deployment addresses and expensive execution controls to anonymous clients.
The project and annotation interfaces in [13-auth-and-security.md](../13-auth-and-security.md) remain
private.

## Decision

Add anonymous `GET /api/v1/public/methods` and `POST /api/v1/public/classify`. Accept exactly one of
`name` or `names`, plus an optional distinct list of deployment-allowlisted methods. Limit batches to
10,000 names and each stripped name to 512 characters. Client method configurations are forbidden.
Operators provide validated method configurations and an allowlist; the default contains local methods
only. Missing configured lookup assets, corrupt bytes, and missing model-manifest members fail acceptance
with a sanitized service-unavailable error. An enabled `local_llm` additionally requires an operator-owned
immutable model revision; its configured model alias must remain bound to those weights. External
OpenAI-compatible endpoints do not provide a general protocol for independently verifying model hashes.

Requests of at most 20 names using only the bounded local rule/lookup methods `gender_guesser` and
`parenthetical_qualifier` return `200` immediately. Larger requests and all other selections atomically
persist a `PublicClassificationJob` and its dispatch-outbox intent, returning `202` and a `Location`.
The response supplies a random retrieval token once; only its SHA-256 digest is persisted.
`GET /api/v1/public/classification-jobs/{id}` requires that token in `X-Classification-Token`, without
requiring an account. Missing and inaccessible jobs return the same `404`. No anonymous job listing
or project data access is added.

Jobs freeze normalized names, selected method versions, validated server configurations, lookup/model
artifact digests, application revision, Python and installed dependency versions, and lock digest at
acceptance. Workers execute that configuration directly through application services. Dedicated worker
routing is persisted; mixed CPU and one dedicated queue use that worker, and incompatible dedicated queues
are rejected. The broker envelope
contains only the job ID. Lease claims and token-fenced terminal writes make redelivery and stale-worker
recovery safe; live workers renew their leases, and completed outputs are immutable. Worker provenance mismatches fail the job rather than
silently executing a different environment. Raw predictions and normalization metadata are retained with
completed jobs. Public responses omit credentials, deployment addresses, raw model diagnostics, and paths.

Synchronous results carry the same method and environment provenance but retain ADR-0028's deliberate
non-persistence semantics. Scientific normalization, reference voting, subset aggregation, confidence,
`unknown`, `abstain`, and `error` behavior is reused unchanged. Report the selected subset explicitly.
The same-origin gateway bounds public request bodies and throttles classification acceptance per address;
direct API deployments must provide equivalent gateway protection.

## Consequences

Callers can classify without accounts while project reads and writes retain existing authentication,
authorization, password-change, and CSRF requirements. Batch clients must retain the retrieval token.
Asynchronous acceptance remains available while Redis is unavailable because dispatch intent is durable.
Publicly enabled slow methods consume worker capacity and require explicit operator configuration.
Public jobs contain submitted names and should be included in deployment backup and retention decisions.
Cross-origin browser integrations and automatic job deletion remain separately scoped future work.
