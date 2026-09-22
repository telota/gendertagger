# ADR-0038: Derive singleton import profiles from source format

**Status:** Accepted

## Context

After [ADR-0037](ADR-0037-remove-pre-production-tei-profiles.md), every supported source format has exactly one
valid import profile. Requiring clients to submit `profile` therefore exposes a choice they cannot make and
retains dispatch machinery for implementations that do not exist. The TEI profile's `_v3` suffix also reflects
the scaffold's development sequence rather than a production compatibility boundary.

The application remains pre-production and has no persisted user data requiring either public identifier.
Snapshot reproducibility still requires the exact importer implementation version and resolved profile to be
persisted after acceptance.

## Decision

Public snapshot-import requests contain `source_format` and `packaging`, but no `profile`. The application
derives `tei_p5_person_register` for TEI and `tei_equivalent_person_register_v1` for CSV, XLSX, and JSON, then
persists the derived value in `SnapshotImportConfig`. Persisted configuration validation rejects a profile that
does not match its source format.

Rename the sole TEI profile from `tei_p5_person_register_v3` to `tei_p5_person_register`. Keep
`tei_parser_v3` as the internal implementation-provenance value: the profile names the supported semantic
mapping, while the parser version identifies the exact implementation that produced a snapshot.

Remove profile parameters, lookup tables, and dispatch branches from the TEI parser and collection importer.
This supersedes ADR-0021's requirement that clients declare a profile and ADR-0037's decision to retain the
`_v3` profile suffix. No migration or compatibility alias is provided; development data must be recreated.

## Consequences

- The multipart API and generated client no longer expose a meaningless profile selector.
- TEI parsing has one direct execution path while snapshots retain explicit importer provenance.
- Adding a genuinely selectable alternative profile later requires a new public-contract and scientific
  decision rather than dormant abstraction now.
- The tabular profile keeps its existing versioned name because renaming it is outside this decision.
