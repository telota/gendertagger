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
- alternative names
- GND ID
- other external identifiers

Preserve source strings. Method-specific preprocessing occurs later in adapters.

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
