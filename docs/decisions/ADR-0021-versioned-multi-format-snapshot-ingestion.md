# ADR-0021: Use versioned formats, packaging, and manifests for snapshot ingestion

**Status:** Accepted

## Context

The asynchronous snapshot-import boundary in
[ADR-0020](ADR-0020-asynchronous-snapshot-import-outbox.md) initially accepts one TEI XML file. Editorial
person registers also arrive as related loose TEI files such as `A.xml` and `B.xml`, ZIP or TAR.GZ bundles,
and CSV, XLSX, or JSON tables. Treating these as additional filename extensions would leave important
semantics undefined: member identity and order, exact-source provenance, cross-file `xml:id` uniqueness,
archive expansion safety, repeated name forms and authority identifiers in tabular data, and the importer
implementation required to reproduce a queued snapshot.

The Schleiermacher register confirms that the canonical projection is hierarchical. A person can have ordered
regular and alternative `persName` forms, repeated `forename` elements, typed GND/VIAF/Wikidata identifiers,
free-text life dates and notes, and ordered events. CSV and XLSX therefore cannot represent the complete
projection through one scalar column per flattened helper field. The source also contains `<sex>` values
produced by earlier gender assignment. Those values are annotations or method outputs, not independent person
input, and importing them into `PersonInput` would risk target leakage.

Archives and XLSX workbooks are untrusted containers. A compressed-byte upload limit alone does not prevent
path traversal, links or device entries, duplicate normalized names, encrypted content, nested containers, or
decompression bombs. Loose multipart files additionally need an immutable aggregate identity and must not be
partially accepted.

## Decision

Snapshot ingestion separates three versioned choices:

- `source_format` describes record semantics: `tei`, `csv`, `xlsx`, or `json`.
- `packaging` describes delivery: `single`, `loose`, `zip`, or `tar_gz`.
- `profile` describes the exact field mapping and importer behavior.

The supported matrix is TEI with all four packaging modes and CSV, XLSX, or JSON as a single file. Unsupported
combinations fail at the public contract boundary. Clients declare all three values explicitly; the server
does not choose scientific semantics from a filename or client-provided media type. New requests default to
TEI, single-file packaging, and `tei_p5_person_register_v3`; the committed v1 and v2 profiles remain explicitly
selectable and keep their original parser versions.

One or more multipart parts named `source` carry the bytes. `single`, `zip`, and `tar_gz` require exactly one
part; `loose` requires one or more parts. Before returning `202 Accepted`, the API validates bounded logical
names and stages every exact upload in content-addressed storage. It then creates all Artifact records, one
pending DatasetSnapshot, ordered source-member rows, and the identifier-only outbox intent in one PostgreSQL
transaction. Database rollback can leave only unreferenced content-addressed blobs, never an accepted partial
collection.

A single file or archive remains the snapshot's primary exact source artifact. A loose collection additionally
stores a canonical JSON manifest as its primary artifact. The versioned manifest records format, packaging,
deterministic member order, safe logical name, SHA-256 digest, byte size, and media type; source-member rows link
that description to the exact member artifacts. Member names are Unicode-NFC normalized and sorted by their
normalized value. Empty names, absolute or parent-traversing paths, backslashes, controls, and collisions after
normalization and case folding are rejected. Each imported PersonRecord records its member and record locator;
legacy records may have null locators.

The CPU worker continues to receive only `dataset_snapshot_id`. It resolves a versioned importer registry from
the persisted source format, profile, packaging, importer version, source members, and the numeric limits that
were active at acceptance. Package reading and record semantics remain separate: the TEI importer sees the same
ordered logical XML documents whether they came from loose artifacts, ZIP, or TAR.GZ. It rejects duplicate
`xml:id` values across the complete collection.

ZIP and TAR.GZ readers never extract into a filesystem tree. They accept only regular XML members and reject
absolute or parent-traversing names, normalized duplicates, encrypted ZIP entries, symlinks, hardlinks, devices,
sparse or otherwise special entries, and nested archives. They enforce persisted limits for member count,
individual and total expanded bytes, and compression ratio both from metadata and while reading. XLSX receives
the same bounded-container treatment. Before Python constructs ZIP member objects, ZIP and XLSX readers inspect
classic EOCD or ZIP64 directory metadata and enforce the persisted member-count limit plus a deterministic
derived central-directory ceiling of `max(64 KiB, member count limit × 16 KiB)`. XLSX securely parses
`[Content_Types].xml`, every relationship part, and worksheet metadata with DTDs, entities, and network access
disabled. Entity-decoded external relationship modes, macro/dialog/VBA parts or content types, formulas,
hyperlinks, merged cells, excessive worksheet dimensions/references, ambiguous populated sheets, and
non-string values are rejected before a read-only streaming workbook load can coerce or materialize them.

The first tabular profile is `tei_equivalent_person_register_v1`. JSON is a top-level array with one object per
person. CSV and XLSX have the same exact columns:

`xml:id`, `persName`, `birth`, `death`, `event`, `note`, `idno`.

JSON uses native arrays for `persName`, `event`, and `idno`; CSV and XLSX store validated JSON arrays in those
cells. A `persName` object preserves `type`, optional `subtype`, and either `name` or `surname` plus ordered
`forename`. An `event` object preserves `type`, optional `when`, and optional `note`. An `idno` object preserves
`type` and `value`. Importers require exactly one regular name, derive all flattened name helpers from the
structured forms, normalize authority identifiers through the same strict routine as TEI v3, reject duplicate
identifier schemes, and preserve scalar strings without date or numeric coercion. CSV is UTF-8 or UTF-8 with
BOM and uses a fixed comma dialect. Unknown, missing, or duplicate fields, excessively large JSON integer
tokens, and strings containing U+0000 are errors rather than silently discarded or deferred to PostgreSQL.

The shared v3/tabular identifier routine recognizes authorities only from exact HTTP(S) hosts and path shapes:
GND uses `d-nb.info` or `www.d-nb.info` with `/gnd/{id}` or the supported legacy `/{id}` form; VIAF uses
`viaf.org` or `www.viaf.org` with `/viaf/{id}`; Wikidata uses `wikidata.org` or `www.wikidata.org` with
`/entity/{id}`. Canonical authority URIs have no user information, port, query, or fragment. A typed bare
authority ID and a same-authority typed canonical URI both become the authority-local ID. `type="uri"` infers
an authority only from those exact forms and otherwise remains ignored. An explicit different safe identifier
scheme retains its value. A declared authority paired with a different authority URI or a non-canonical URI is
invalid, and duplicate normalized schemes invalidate the person record. Hostname substrings and lookalike or
suffix hosts never identify an authority. TEI v1 deliberately retains its historical projection unchanged;
the committed TEI v2 projection also remains unchanged, including its broader historical URI matching. The
strict behavior applies only to TEI v3 and the tabular profile.

TEI v3 also projects ordered direct `<event>` values into `PersonInput`; TEI v1 and v2 remain reproducible and
do not gain new captured structure. Direct `<sex>` is deliberately excluded from `PersonInput` and the
tabular profile. The exact source remains available, and a future label or annotation importer must map source
gender claims into the auditable annotation/evaluation model explicitly instead of presenting them to
classifiers as input features.

TEI v3 inserts safe text boundaries when otherwise adjacent visible descendant segments would concatenate,
so `van<nameLink/>Helsing` projects as `van Helsing`; comments and processing-instruction payloads remain
excluded. Component markup is limited to the corpus-supported inline `<name type="…">`, nested keyed
`<persName>`, and empty `<nameLink/>` forms, and other descendants are rejected rather than flattened. TEI v1
and v2 retain their historical separator-free descendant concatenation; v2 also retains its committed
descendant flattening, authority handling, and empty event projection under `tei_parser_v2`. These scientific
normalization changes therefore require `tei_parser_v3` rather than reinterpreting an existing snapshot.

All package validation, parsing, PersonRecord writes, and the ready transition retain ADR-0020's atomic import
transaction. Permanent format or contract errors produce a sanitized failed snapshot; transient source reads
and infrastructure errors retry from the immutable source. Successful snapshots are equivalent when their
canonical PersonInput projections are equivalent, while their distinct exact sources and manifests remain
fully attributable.

## Consequences

- The API supports the declared TEI collection/archive and single-file tabular matrix without multiplying
  format-specific endpoints or Celery messages.
- Loose collections have durable, deterministic aggregate provenance; archives retain their exact container
  bytes and deterministic validated member order.
- CSV/XLSX users must encode hierarchical TEI fields as JSON arrays rather than maintaining inconsistent flat
  and structured name columns.
- New TEI imports default to v3, while explicit v1 and v2 imports preserve their published parser behavior and
  cannot gain v3 normalization under an old parser version.
- Historical date strings and identifiers are not silently transformed by spreadsheet libraries.
- Existing source `<sex>` annotations cannot leak into gender methods. Importing those annotations remains a
  separate scientific workflow requiring its own contract and decision.
- Limits are part of persisted import provenance, so a queued snapshot is not reinterpreted merely because a
  worker deployment changes its environment settings.
- Large collections still hold one database transaction during import. Observable progress, cancellation, and
  chunked atomic publication require a future attempt/staging design rather than weakening snapshot
  immutability.
- Failed acceptance may leave unreferenced content-addressed blobs. Reference-aware garbage collection with a
  grace period remains an operational capability; it must never delete bytes concurrently being accepted.

Possible extensions beyond this accepted contract are tracked in
[`16-open-questions.md`](../16-open-questions.md), including artifact garbage collection, HTTP acceptance
idempotency, resumable progress and cancellation, object-storage staging, and additional tabular packaging.
They are not prerequisites for the supported matrix defined by this decision.
