# Resolved design questions

The main architecture is decided. This document records the questions that were genuinely open
during design and how the implemented system resolved them, so that the resolution is not rediscovered
or silently reversed.

Expansion candidates that remain deliberately unimplemented are recorded in
[`22-future-development.md`](22-future-development.md) rather than here.

## Authentication identity provider

Resolved in two steps. First, the provider was made pluggable. Browser mechanics are fixed:
same-origin secure HTTP-only session cookies, with CSRF validation required for every unsafe method
on the `/api/v1` router. `AuthenticationBackend` is a protocol, and every backend terminates into the
same `CurrentUser` abstraction, so local accounts and institutional SSO need no divergent
authorization path.

Second, the default provider was chosen: `DatabaseAuthenticationBackend`, a local account system with
admin-provisioned users, Argon2id password hashes, and revocable server-side sessions
([ADR-0031](decisions/ADR-0031-local-database-authentication.md)). Institutional SSO remains a later,
additive backend. See [`13-auth-and-security.md`](13-auth-and-security.md).

## Exact batch sizes and concurrency

Resolved as a server-side property rather than a client input. Each `MethodRegistration` in
`gendertagger.services.method_registry` carries its own `batch_size` and routing queue, and
`plan_task_batches` partitions a run's records with it. The resulting partition is durable: each
TaskBatch persists its own offset and count, so the executed partition remains reconstructible even
if the registry default changes later. Tuning the numbers per method from measurements is an
operational activity, not an open design question.

## TEI project profiles

Resolved through explicit versioned profile enums rather than corpus-specific conditionals spread
through core code. Ingestion selects `TeiImportProfile` (`tei_p5_person_register_v1` through `v3`,
defaulting to `v3`) or `TabularImportProfile`; export selects
`TeiExportProfile.tei_p5_gender_v1`. An edition with a different TEI structure or gender vocabulary
is served by adding a new profile value, which keeps earlier projections reproducible unchanged. See
[`08-ingestion-and-export.md`](08-ingestion-and-export.md).

## Reference aggregation before alternatives

Resolved in favour of reproducing the published reference behavior first. `AggregationStrategy`
admits the versioned reference strategy, and the golden fixtures gate it. Weighted and experimental
strategies were deferred rather than designed speculatively into the first implementation; they are
recorded in [`22-future-development.md`](22-future-development.md).

## Snapshot ingestion scope

Resolved. The asynchronous import contract is complete for TEI in `single`, `loose`, `zip`, and
`tar_gz` packaging, and for single-file CSV, XLSX, and JSON. The capabilities that were previously
listed here as ingestion expansion candidates — reference-aware artifact garbage collection,
idempotent HTTP snapshot acceptance, observable/resumable import progress and cancellation, shared
object storage, and additional tabular packaging — are optional expansions rather than unfinished
acceptance criteria. Each carries constraints that must survive into any future implementation, so
they are recorded in full in [`22-future-development.md`](22-future-development.md).
