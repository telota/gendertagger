# ADR-0017: Preserve structured TEI person-name forms additively

**Status:** Accepted

## Context

The first TEI person-register profile projects one regular surname, ordered forenames, and alternative names
onto flat `PersonInput` fields. These fields are already part of the public Pydantic and OpenAPI contracts,
PostgreSQL persistence, review search, method inputs, and prediction-input fingerprints. They remain useful
stable projections for classification and tabular exchange.

The Schleiermacher person register demonstrates that the flat alternative-name projection is not a complete
source representation. A direct `<person>/<persName>` may use either `<name>` or separate `<surname>` and
`<forename>` children; several alternative forms may occur in source order; and `@subtype` distinguishes such
forms as `birthname` or `pseudonym`. Flattening the entire `<persName>` element into one string loses the
component boundaries and subtype. It can also make insignificant XML formatting significant: adjacent
`</surname><forename>` markup produces a concatenated value when text nodes are joined without an explicit
component separator.

An audit of the 26 Schleiermacher register files found 8,157 people. Every person has exactly one direct
regular name. Of 1,358 direct alternative forms, 375 use separate surname/forename components and 983 use a
single name component; 546 are marked `birthname` and 10 `pseudonym`. Nineteen regular forms also use a single
name component. The corpus therefore requires both representations and repeatable ordered alternatives rather
than a single structured primary name plus string aliases.

Replacing `alt_names: list[str]` with structured objects would break existing API consumers, review search,
stored rows, and method contracts. A union of strings and objects would make the canonical contract ambiguous.
Backfilling structured forms from the flat values would invent information, while reparsing into existing
ready snapshots would violate [ADR-0002](ADR-0002-immutable-dataset-snapshots.md).

## Decision

`PersonInput` and `PersonRecord` retain the existing `surname`, `forenames`, and `alt_names` fields unchanged.
They gain an additive `name_forms: list[PersonNameForm] | None` field. `PersonNameForm` represents one direct TEI
`<persName>` in document order and carries:

- `type`, restricted by this profile to `reg` or `alt`;
- the source `subtype`, when present, without reducing project-specific values to a closed enum;
- the normalized direct text or direct `<name>` value, when the form uses an unstructured name;
- the direct `<surname>` value and ordered direct `<forename>` values, when the form is structured.

The parser reads only `<persName>` elements that are direct children of `<person>`. Nested `<persName>` elements
inside notes, events, or other descriptive content are references in that content and are not person-name
forms. Source order is preserved for `name_forms` and for repeated forenames. Text normalization remains the
existing whitespace-only helper normalization. Empty components collapse to absence, empty `<nameLink/>`
placeholders and editorial processing instructions are not projected, and inline component markup is flattened
to text. Non-empty unsupported direct structures are rejected rather than silently discarded. The immutable
source artifact remains the lossless XML record. Attributes on direct name components are rejected when the
profile cannot represent them; attributes on supported nested inline markup remain available in the artifact.

`name_forms=None` means that the importing parser profile did not capture structured name forms. This is the
representation for existing `tei_p5_person_register_v1` records and manually constructed legacy-compatible
inputs. A populated list means that a structured-name-aware profile examined the record; the v2 contract
requires exactly one regular form. This distinction prevents absence of legacy metadata from being
misrepresented as observed source absence.

The new `tei_p5_person_register_v2` profile is the default for new imports. It populates `name_forms` and derives
the retained flat fields deterministically. V1 remains explicitly selectable for historical reproduction. The
single direct regular form supplies `surname` and `forenames`; a regular unstructured name retains the v1
compatibility projection into `surname`. Each unstructured alternative supplies one `alt_names` value. A
structured alternative supplies one value by joining its non-empty surname and forenames with one space,
independent of indentation or adjacent XML tags. Alternative forenames are not merged into the regular
`forenames` method input. A future method may use name forms only through an explicitly versioned scientific
change.

Persistence adds a nullable JSONB `name_forms` column to `person_records`. JSONB is appropriate for this
bounded source-provenance structure because the existing flat columns remain the query and search projection.
Repository boundaries validate JSONB values through `PersonNameForm`; storage rows are never exposed as the
contract. Existing ready snapshots remain null and are not backfilled. Obtaining structured forms for an old
artifact requires a new import and therefore a new immutable DatasetSnapshot under the v2 profile.

Prediction-input fingerprinting is profile compatible. When `name_forms` is `None`, the fingerprint uses the
v1 field projection and omits the new field, preserving legacy fingerprint semantics. When `name_forms` is a
populated list, the canonical v2 fingerprint includes the complete ordered structured value. The snapshot's
persisted parser version and import profile identify which extraction and fingerprint semantics apply.

## Consequences

- Existing flat-name API consumers, review search, classifiers, and v1 snapshots remain compatible.
- V2 imports preserve regular and alternative component boundaries, source order, and alternative-name
  subtype without making the relational projection a lossless TEI syntax tree.
- The flat and structured representations are deliberately redundant. Parser and contract tests must enforce
  their deterministic v2 projection so they cannot diverge silently.
- Correcting XML-boundary-dependent alternative-name strings occurs only in v2 snapshots; historical ready
  snapshots and their predictions are not rewritten.
- V2 structured names intentionally participate in prediction provenance even if a current adapter uses only
  the flat regular-name projection.
- Querying by regular surname, forename, or flattened alternative name continues to use ordinary columns. If
  subtype- or component-level queries later become a core requirement, a reviewed relational projection or
  index can be added without changing the Pydantic source contract.
