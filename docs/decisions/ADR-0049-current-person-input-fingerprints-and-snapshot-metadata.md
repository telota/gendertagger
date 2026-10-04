# ADR-0049: Current person-input fingerprints and snapshot metadata

**Status:** Accepted

## Context

The execution path removes null structured names and empty events from fingerprint payloads to preserve
an earlier encoding. Snapshot statistics can be reconstructed partially from stored authority IDs, and
missing persisted packaging is interpreted as `single`. These compatibility paths hide differences
between current canonical contracts and incomplete historical evidence. The
[persistence specification](../04-persistence.md), [ingestion specification](../08-ingestion-and-export.md),
and [provenance specification](../11-provenance-and-reproducibility.md) require immutable snapshots and
outputs with reproducible inputs. The approved BQ-06 cutover retires these paths without changing scientific
classification or rewriting sealed historical rows.

## Decision

1. Fingerprint every canonical `PersonInput` field in JSON mode, including defaults, nulls, and empty
   collections, with the existing canonical-JSON SHA-256 implementation. Preserve source order in lists;
   object key order is immaterial. Do not include PersonRecord persistence identity, snapshot identity,
   source-member/record locators, or creation time. Do not special-case absent names or empty events.
2. Identify the fingerprint representation through the accepted Run source revision and matching actual
   worker provenance established by [ADR-0048](ADR-0048-project-worker-provenance-compatibility.md).
   Do not introduce a parallel hash-version field, compatibility algorithm, or alias. Existing Predictions
   keep their recorded fingerprints and environments; only newly accepted Runs use the current encoding.
3. A ready snapshot must have persisted, validated `DatasetSnapshotStatistics` belonging to that snapshot
   and agreeing with its record count. Missing statistics fail with the existing invalid-resource-state
   contract. Never reconstruct GND coverage at read time. Non-TEI imports still materialize statistics with
   source-gender capture explicitly unavailable; unavailable capture is not a missing statistics resource.
4. `SnapshotImportRequest` retains its public format and packaging defaults. `SnapshotImportConfig` is the
   resolved persisted contract: source format, packaging, profile, and limits are required explicitly.
   Acceptance resolves request defaults before storage. Import and repository boundaries reject missing
   stored choices instead of substituting current defaults.
5. Recover incomplete development snapshots through a new import, new snapshot identity, and new Runs
   where classification is needed. Reuse exact retained source bytes when available. A disposable synthetic
   seed without real source bytes may be regenerated from its persisted synthetic inputs, but the new
   source must be identified as generated synthetic data, never as the unavailable historical artifact.
   Preserve old snapshots, Predictions, annotation history, source metadata, and other scientific artifacts.
   Complete snapshots do not need reimport merely because new Runs use a different fingerprint encoding.
6. Keep labels, normalization, authority precedence, aggregation, certainty tiers, TEI output semantics,
   evaluation definitions, and scientific fixtures unchanged. No database schema migration is needed:
   current imports already store the required inventory and resolved configuration.

## Consequences

Current fingerprints cover the complete model rather than an old field subset. Existing cached or stored
hashes may differ despite equivalent flat name fields; they remain historical evidence, not values to
backfill. Required persisted choices distinguish an accepted default from missing provenance. Ready
statistics reads are bounded to the stored inventory rather than querying person identifiers.

Operators must reimport incomplete snapshots before using current statistics or guarded import paths.
This deliberately rejects silent repair and in-place development resets, preserving immutable evidence
at the cost of retaining obsolete development resources. Behavioral coverage must prove input-field
significance, persistence-field exclusion, deterministic hashing, strict metadata failures, valid stored
statistics, unchanged public defaults, and actual imported/persisted outputs under the new contract.
