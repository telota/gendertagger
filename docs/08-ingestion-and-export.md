# TEI ingestion and export

## Import model

Every import creates a new immutable DatasetSnapshot under a Project.

Pipeline:

```text
source TEI artifact
  -> XML parse/validation
  -> extract person records
  -> preserve canonical xml:id
  -> normalize selected helper fields
  -> compute hashes/fingerprints
  -> persist PersonRecords
  -> mark snapshot ready
```

A failed import does not partially become a ready snapshot.

## Source preservation

Always retain the exact input artifact (or an immutable content-addressed reference) and its SHA-256 hash.
Do not make the flattened relational representation the only surviving source.

## Extracted fields

Reference extraction supports:

- `xml:id`
- surname
- forename(s)
- vital dates
- biographical note/context
- flattened alternative names
- ordered structured direct `<persName>` forms when the selected profile supports them
- GND ID
- other external identifiers

Preserve source strings. Method-specific preprocessing occurs later in adapters.

The v2 profile recognizes canonical GND URLs, legacy `d-nb.info/<id>` GND URLs, Wikidata URLs, VIAF URLs, and
explicitly typed identifiers. Authority URIs are projected to their authority-local identifier while the exact
URI and any surrounding editorial processing instructions remain in the immutable source artifact. Empty
`<idno>` elements do not produce identifiers.

## Person-name profiles

`tei_p5_person_register_v1` preserves the historical flat projection: one regular `surname`, ordered regular
`forenames`, and flattened `alt_names`. Its records have `name_forms=None`, which means structured person-name
forms were not captured rather than that the source contained none.

`tei_p5_person_register_v2`, the default for new imports, additionally records every direct
`<person>/<persName>` in document order. Each `PersonNameForm` preserves `@type`, optional `@subtype`, and either
an unstructured value from direct text or `<name>`, or direct `<surname>` and ordered `<forename>` values. The
parser does not treat nested `<persName>` references inside `<note>`, `<event>`, or other descriptive content as
alternative names. Callers may still select v1 explicitly when reproducing a historical import.

V2 continues to populate the flat fields for existing methods, search, and simple tabular exchange. The first
regular form supplies the regular surname and forenames; a regular `<name>` retains the v1 projection into
`surname`. An alternative `<name>` becomes one flat alternative value. For a structured alternative, the
parser joins non-empty surname and forename components with one space, so XML indentation and adjacent tags do
not affect the result. Alternative forenames are not merged into the regular `forenames` method input.

The structured projection is source-rich but not an XML syntax tree. Empty name components are normalized to
absence, empty `<nameLink/>` placeholders and editorial processing instructions do not become model fields,
and inline markup inside a component becomes its normalized text. Unsupported direct component elements or
attributes are rejected rather than silently discarded. The immutable artifact retains the exact syntax.

Structured names participate in v2 person-input fingerprints in their complete source order. When
`name_forms` is null, fingerprinting retains the v1 projection and omits the new field. Existing ready
snapshots are never reparsed or backfilled; obtaining structured forms from a preserved v1 artifact creates a
new immutable snapshot under v2. See
[ADR-0017](decisions/ADR-0017-structured-tei-person-name-forms.md).

## Snapshot comparison

Because `xml:id` is canonical inside a Project, later tooling can compare snapshots by `(project_id, tei_id)` and report added/removed/changed records. This is useful but not required for the first vertical slice.

## TEI export

The reference encoding uses a child `<gender>` element on `<person>`, not a shorthand attribute, so the annotation can carry provenance and certainty.

Shape:

```xml
<gender value="female"
        evidence="assigned"
        resp="#gendertagger"
        cert="low"/>
```

Reference semantics:

- `@value`: canonical label
- `@evidence="assigned"`
- `@resp="#gendertagger"` for automated decisions
- human-reviewed decisions use the configured human/editor responsibility identifier
- `@cert` uses TEI values `high`, `low`, `unknown`

Insertion position for the reference profile: after the last `<persName>` and before `<birth>`, `<death>`, or `<note>` children.

## TEI certainty projection

Keep the richer internal certainty tier. Export a deterministic projection to TEI:

- internal `high` -> `high`
- internal `low` -> `low`
- `contested`, `single`, `uncertain`, `no_data` -> `unknown`
- a human-reviewed final decision -> `high`

If the project later adopts a different TEI profile, implement it as a versioned export profile rather than changing historical exports.

## Export modes

Support at least:

1. TEI with selected machine aggregation
2. TEI with human overrides/final decisions
3. JSON result bundle
4. CSV analysis export
5. provenance/run manifest alongside all exports

Never mutate the original source artifact in place.
