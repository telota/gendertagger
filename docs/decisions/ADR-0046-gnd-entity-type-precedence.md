# ADR-0046: GND entity-type precedence

**Status:** Accepted

## Context

[ADR-0023](ADR-0023-content-addressed-sqlite-method-lookups.md) and the
[normative scientific specification](../07-methods-and-aggregation.md#versioned-lookup-data) reserve
GND male/female classification for persons, classify corporate bodies as institutions, and require
other retained entity types to yield substantive unknown.

The original adapter only special-cased corporate bodies. Because the compiler derives entity type
and gender independently, a synthetic place record with MARC gender code `1` produced `success + male`.
That result could become a GND authority override rather than allowing the pooled reference vote.
The user authorized correcting the implementation now. This is conformance with the accepted rule,
not a new aggregation strategy or evidence that a production snapshot contains affected records.

## Decision

Apply this order at the runtime GND adapter boundary:

1. No input GND ID or no matching snapshot row emits `no_gnd` and abstains.
2. A corporate-body row emits `organisation`, normalized to `institution`, regardless of gender.
3. A person row uses its compiled gender label, including `Unbekannt` when gender is unrecognized.
4. Every other entity type emits `Unbekannt`, normalized to `success + unknown`, regardless of the
   compiled gender label.

Retain the original source gender label/URI, normalized and raw entity types, lookup-match evidence,
preferred name, and record status in raw output. Do not erase contradictory source evidence or
convert a matched non-person record into abstention or technical error.

Use implementation version `gnd_v2`. Retain method identifier `gnd`, normalization `gnd_v1`, the
closed digest-based configuration, lookup schema/compiler versions, and reference authority order.
No database migration or lookup recompilation is required. Existing snapshots, predictions, and
recorded execution descriptors remain immutable; newly accepted executions record the new adapter
version. Pending old executions must run with their recorded implementation, not a mixed-version
worker deployment.

## Consequences

Recognized gender on non-person/non-corporate records no longer creates an authority override.
Person classification, corporate-body classification, missing-ID/row abstention, normalization,
confidence, and source-evidence retention remain unchanged.

Regression coverage must exercise both recognized genders across non-person entity families using
compiled SQLite snapshots, preserve contradictory source evidence, and check corporate-body
precedence. Existing scientific golden expectations are not rewritten to conceal a changed result.
The separate worker-provenance compatibility gap is not repaired by this adapter correction.
