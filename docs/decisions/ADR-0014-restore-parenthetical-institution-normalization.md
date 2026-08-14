# ADR-0014: Restore parenthetical institution normalization

**Status:** Accepted

## Context

[ADR-0003](ADR-0003-reference-aggregation.md) requires the default aggregation to reproduce the published
four-label behavior, including `institution`, with the parenthetical-qualifier method as the highest-priority
authority. The legacy method emitted `institution` for organizational name qualifiers such as `Firma` and
`Bankiers`.

[ADR-0010](ADR-0010-parenthetical-qualifier-adapter.md) instead left `institution` out of the
`parenthetical_qualifier_v1` normalization map. That decision relied on an eight-record fixture containing no
parenthetical institution case. A replay of all 8,277 preserved records found seven organizational qualifiers
whose normalized outcome consequently became an abstention. Six retained their final label through another
method but changed certainty; `S1122134` also changed its final label and agreement score.

No externally depended-on run or release uses the defective behavior. The project remains at version `0.0.0`
in active development.

## Decision

Supersede ADR-0010's decision to normalize a raw parenthetical `institution` label as an abstention. The
existing `parenthetical_qualifier_v1` profile maps it to canonical `institution` with prediction status
`success`. The `reference_v1` aggregation therefore applies the published parenthetical authority override.
Raw labels, matched evidence, and normalization provenance remain preserved.

Correct the existing normalization version in place rather than introduce `parenthetical_qualifier_v2`.
Versioning an unreleased defect would make the incorrectly characterized behavior part of the supported
scientific contract. Add `S1122134` and `S1619063` to both paired scientific fixtures so normalization,
override selection, disagreement, agreement, and certainty are tested together.

## Consequences

- `reference_v1` again represents the published parenthetical institution override.
- Development results produced with the defective profile must be recomputed; they are not a supported
  compatibility target.
- The paired scientific fixture now covers parenthetical institution alongside unknown and abstention; adapter
  tests cover all four canonical outcomes.
- All other parenthetical matching, normalization, and aggregation behavior remains unchanged.
