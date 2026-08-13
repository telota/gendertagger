# Remaining open questions

The main architecture is decided. These are deliberately non-blocking or implementation-time choices.

## Authentication identity provider

Browser mechanics are decided: same-origin secure HTTP-only session cookies plus CSRF protection. The concrete identity provider is still open. Options include local accounts for the first deployment or integration with institutional SSO/OIDC; both should resolve to the same `CurrentUser` abstraction.


## Artifact backend

Filesystem is the initial backend. S3/MinIO remains an optional later adapter, not a v1 requirement.

## Exact batch sizes/concurrency

Tune per method from measurements. Preserve them in MethodExecution configuration/provenance.

## Alternative aggregations

The system should eventually permit weighted or experimental strategies, but the first implementation must reproduce the unweighted published reference strategy.

## TEI project profiles

The reference export profile is documented. If additional editions use different TEI structures or gender vocabularies, introduce explicit import/export profiles rather than corpus-specific conditionals throughout core code.

## Cross-snapshot annotation semantics

A human annotation is made in a snapshot context but the `xml:id` is canonically stable within a project. Decide later whether verified decisions should be suggested/carried forward to a newer snapshot when the relevant person record is unchanged. Never carry them silently.

## Cache retention

Define operational retention/eviction after real workload sizes are known.
