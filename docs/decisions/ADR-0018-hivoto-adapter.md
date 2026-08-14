# ADR-0018: HIVOTO local-snapshot adapter

**Status:** Accepted

The direct-path dataset selection and per-worker source parsing in this decision are superseded by
[ADR-0023](ADR-0023-content-addressed-sqlite-method-lookups.md). The frozen spelling expansion, majority vote,
certainty reduction, and normalization behavior remain accepted.

## Context

`hivoto` is the fourth Phase 5 method. It resolves forename tokens against a lookup index built from a
local HIVOTO historical first-name dataset — a large semicolon-delimited snapshot that is not
redistributable and not needed by the core service. The legacy pipeline read the snapshot with pandas,
mapped each row's `Namensgeschlecht` to a raw label, aggregated repeated names by majority vote, and
reduced the per-token labels by the shared consensus. It reuses the name-based adapter pattern from
[ADR-0012](ADR-0012-name-based-classifier-adapter-pattern.md) and the frozen `hivoto_v1` profile. See
[methods and aggregation](../07-methods-and-aggregation.md).

## Decision

Port `map_gender` and the majority-vote index build verbatim, replacing the pandas read with the standard
library `csv.DictReader` (`;` delimiter, `utf-8-sig`) so the adapter needs no new runtime dependency. Each
row contributes its original and classified spellings as keys (the classified spelling stripped of a
trailing period); a name seen multiple times takes the majority-vote gender with ties broken by the index
priority, and its certainty is `sicher` only when every entry agrees, otherwise `mittlere Sicherheit`.
Per token the adapter lowercases and strips trailing punctuation, looks the key up (falling back to
`unknown`), takes the priority consensus over the per-token genders, and normalizes against the frozen
`hivoto_v1` profile. Certainty is preserved in raw output as provenance and never affects the vote; the
adapter reports no `method_confidence`.

The snapshot is selected by required resolved run configuration (`dataset_path`), recorded in provenance,
as a direct filesystem path pending the GND snapshot-resolution model. The index backend is injectable for
testing and cached per dataset path.

## Consequences

- Reproduces the legacy `hivoto` output exactly on all 8277 reference-corpus records.
- Replacing pandas with the standard library keeps the dependency surface unchanged; the empty-cell key
  that pandas materialized as the literal string `"nan"` is skipped instead, which changes no
  reference-corpus token outcome.
- The large snapshot stays out of version control and is supplied per deployment through configuration,
  keeping the exact dataset reproducible from provenance.
- Certainty remains descriptive provenance, preserving the separation between method output and the vote.
- The direct-path configuration is provisional and may adopt the GND versioned snapshot resolution under a
  later ADR; the raw label and normalization stay fixed.
