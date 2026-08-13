# ADR-0010: Parenthetical-qualifier rule adapter

**Status:** Accepted

## Context

Phase 4 must run at least one cheap classification method asynchronously end to end, but no method adapter
existed yet. The parenthetical-qualifier rule is the first method in the Phase 5 migration order and the
cheapest: it is a pure, deterministic, CPU-only rule with no model, network, or authority dependency. Its
`parenthetical_qualifier_v1` normalization profile and golden fixtures were already frozen in Phase 1, so the
only new scientific surface is the raw-label rule itself. Bringing it up now exercises the execution
architecture on a genuine method instead of a throwaway placeholder.

The legacy rule scanned parenthetical relational qualifiers in a person's name fields and the first word of an
editorial note (`Frau des`, `Sohn des`, `Familie`, `Firma`, ...). It could emit `female`, `male`, `unknown`
(family group), `institution`, or no answer. The frozen `parenthetical_qualifier_v1` profile deliberately maps
only `female`, `male`, and `unknown`; it does not map `institution`.

## Decision

Port the legacy rule verbatim as `ParentheticalQualifierMethod`, preserving its keyword sets, its ordered
first-word-then-any-word matching within each parenthetical, its scan order (surname then forenames then note),
and its note-first-word-only, never-institution behavior. The adapter emits the raw rule label and defers every
canonical outcome to `normalize_raw_label` against the frozen `parenthetical_qualifier_v1` profile, keeping raw
method output and normalization provenance separable.

A missing qualifier produces raw label `None`, which normalizes to `abstain`. Because the frozen profile does
not map `institution`, a legacy `institution` raw label normalizes to `abstain` with reason `unparseable`; the
raw evidence is still preserved on the prediction. The adapter reports no `method_confidence`, because the rule
is deterministic and its historical constant confidence is not a calibrated probability. `implementation_version`
is `parenthetical_qualifier_v1` and is versioned independently of the normalization version.

## Consequences

- The end-to-end asynchronous path runs a real, golden-tested method with no throwaway code.
- Reference behavior is unchanged: the eight frozen fixture cases only exercise the `abstain` and substantive
  `unknown` outcomes, which are preserved exactly.
- Institution detection remains latent: the rule still recognizes organisational qualifiers, but the frozen
  profile drops them to `abstain`. Promoting parenthetical `institution` to a canonical outcome is a future
  normalization-version change requiring its own fixture update and ADR, not a silent adapter change.
- Splitting a single legacy forename column into TEI `forenames` is handled by scanning each forename in order,
  which cannot change any single-field fixture outcome.
