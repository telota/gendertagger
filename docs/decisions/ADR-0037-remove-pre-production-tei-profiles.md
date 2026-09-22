# ADR-0037: Remove pre-production TEI import profiles

**Status:** Accepted

The public-selection and profile-naming portions are superseded by
[ADR-0038](ADR-0038-derive-singleton-import-profiles.md); removal of the older implementations remains accepted.

## Context

The repository accumulated three TEI profiles while the import contract was being developed. V1 retained a
flat name projection, v2 added structured names, and v3 added events, strict authority normalization, safe
text boundaries, and explicit markup validation. Supporting all three expanded the public enum, parser,
persistence invariants, tests, and documentation.

The application has not been deployed to production and has no older persisted snapshot data to reproduce.
The compatibility rationale in [ADR-0017](ADR-0017-structured-tei-person-name-forms.md) and
[ADR-0021](ADR-0021-versioned-multi-format-snapshot-ingestion.md) therefore does not apply to real users or
durable production provenance.

## Decision

`tei_p5_person_register_v3` is the only supported TEI import profile. Remove the v1 and v2 enum values,
extractors, version constants, compatibility invariants, public-schema alternatives, and behavior-specific
tests. Imported TEI records must contain the structured name forms produced by v3; they may contain its
ordered event projection.

Keep the v3 name and `tei_parser_v3` provenance value. Renaming the current behavior would create needless
provenance churn and obscure which normalization rules are implemented. Other independently versioned
contracts, including `tei_equivalent_person_register_v1`, are unaffected.

No data migration or compatibility reader is provided. Development databases or fixtures containing a v1 or
v2 import profile must be recreated and their source artifacts re-imported. This decision supersedes only the
v1/v2 retention portions of ADR-0017 and ADR-0021; their structured-name, ingestion, packaging, safety, and
provenance decisions remain in force.

## Consequences

- The public API accepts one TEI profile and generated clients expose one TEI enum value.
- Parser and repository behavior describe the current scientific projection without dormant compatibility
  branches.
- Old development-only snapshot rows are intentionally unsupported rather than silently reinterpreted.
- Removing a persisted profile after production deployment would require a separate migration and
  compatibility decision; this pre-production simplification does not establish that as a general policy.
