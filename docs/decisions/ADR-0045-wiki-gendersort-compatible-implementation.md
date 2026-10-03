# ADR-0045: Wiki-Gendersort compatible implementation

**Status:** Accepted

## Context

[ADR-0013](ADR-0013-wiki-gendersort-adapter.md) selected a verbatim port of the upstream name-cleaning and
assignment routines. The publication review found no recorded redistribution permission, and the user
reports that the original author cannot be reached. The user authorized a behavior specification,
independently developed replacement, exact-output comparison, and measured optimization.

The scientific method and its normalization remain normative. A source rewrite must preserve candidate
order, transliteration quirks, native-label priority, matched-name evidence, and full prediction behavior.
The existing four cleaner examples alone do not establish equivalence.

## Decision

Supersede the verbatim-port implementation choice with a replacement developed from
[the behavior specification](../29-wiki-gendersort-compatibility.md). Keep source examination and private
comparison separate from the implementation conversation. Record that the specification author examined
the old source; this process is not itself a legal-clearance determination.

Use implementation version `wiki_gendersort_v2`. Retain method identifier `wiki_gendersort`, normalization
version `wiki_gendersort_v1`, existing configuration, lookup schema/compiler versions, native and canonical
labels, per-token consensus, and raw-output fields. Keep the immutable SQLite provisioning and batching
decision in [ADR-0023](ADR-0023-content-addressed-sqlite-method-lookups.md). Existing persisted predictions
are never rewritten, and old scheduled work must execute with its recorded worker implementation.

Establish compatibility using synthetic edge cases, deterministic generated inputs, exact native and
matched-name comparisons, and the full preserved reference corpus when locally available. Keep the old
comparison implementation outside published source and packages. Reuse identical tokens within a batch
and bounded character properties only after compatibility verification and a measured benefit. Preserve
scientific output rather than changing quirks as part of optimization.

## Consequences

The current runtime no longer needs the copied routines or a new upstream software dependency. Method
implementation provenance identifies the replacement independently of unchanged normalization and data
artifact identities. Scientific attribution remains required.

Compatibility evidence and benchmark measurements must state their inputs and limits. Full tests,
static analysis, package checks, and distribution inspection remain required. Mixed worker deployments
must not execute old scheduled work under a new implementation identity.

Historical copied source and the lookup table's rights remain separate publication questions. Source
replacement alone does not close RG-04 or authorize redistribution of an original or compiled table.
