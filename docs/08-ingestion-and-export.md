# Snapshot ingestion and TEI export

## Import model

Every import creates a new immutable DatasetSnapshot under a Project.

Pipeline:

```text
one or more declared source uploads
  -> bounded content-addressed artifact(s) and optional manifest
  -> pending snapshot + outbox intent
  -> 202 Accepted
  -> CPU import worker
  -> package and record validation
  -> extract person records
  -> preserve canonical xml:id
  -> normalize selected helper fields
  -> compute hashes/fingerprints
  -> persist PersonRecords
  -> mark snapshot ready
```

A failed import does not partially become a ready snapshot.

## Asynchronous import lifecycle

The API accepts declared TEI, CSV, XLSX, and JSON person-register sources. It receives, bounds, hashes, and
durably stores every complete upload before returning because a worker cannot reopen request-temporary files.
The Artifact records, ordered source-member provenance, pending DatasetSnapshot, and identifier-only outbox
intent then commit together. A loose TEI collection also receives an immutable aggregate manifest.
`202 Accepted` returns that pending snapshot; it does not wait for package inspection, record validation, or
PersonRecord persistence.

The CPU worker resolves the Artifact set, manifest, import configuration, accepted limits, and importer version
from the snapshot ID in its task message. Its conditional claim, package validation, streamed parse,
PersonRecord writes, and ready transition form one transaction at the current source scale. Bounded flush
groups control individual inserts but do not commit partial data. A permanent parse failure rolls back before
the snapshot is marked failed, while a transient failure rolls back to pending for retry. See
[ADR-0020](decisions/ADR-0020-asynchronous-snapshot-import-outbox.md) and
[ADR-0021](decisions/ADR-0021-versioned-multi-format-snapshot-ingestion.md).

## Source preservation

Always retain the exact input artifact (or an immutable content-addressed reference) and its SHA-256 hash.
Do not make the flattened relational representation the only surviving source.

Single files and uploaded archives remain the primary exact Artifact. For a loose TEI collection, every exact
file is an Artifact and the primary Artifact is canonical compact JSON containing the manifest version,
declared format and packaging, and each member's deterministic order, safe logical name, checksum, size, and
media type. SnapshotSourceMember rows connect that manifest to the exact member Artifacts. Each PersonRecord
also stores its member name and record locator.

The API and CPU worker must address the same immutable artifact-storage namespace. Task messages and public
responses contain resource IDs rather than storage URIs or filesystem paths.

## Extracted fields

Reference extraction supports:

- `xml:id`
- surname
- forename(s)
- vital dates
- biographical note/context
- ordered typed events with optional `when` and note
- flattened alternative names
- ordered structured direct `<persName>` forms when the selected profile supports them
- GND ID
- other external identifiers

Preserve source strings. Method-specific preprocessing occurs later in adapters.

The v3 profile recognizes authority URLs only by exact host and path: GND on `d-nb.info` or `www.d-nb.info`
with `/gnd/{id}` or the supported legacy `/{id}` path, VIAF on `viaf.org` or `www.viaf.org` with `/viaf/{id}`,
and Wikidata on `wikidata.org` or `www.wikidata.org` with `/entity/{id}`. HTTP and HTTPS are accepted; user
information, ports, queries, fragments, lookalike hosts, and hostname substrings are not authority matches.
Typed bare IDs and same-authority canonical URIs are projected to their authority-local identifier. A generic
unknown URI is ignored, an explicit other safe scheme is preserved, and a declared authority that conflicts
with the URI authority or supplies a non-canonical URI fails the record. Duplicate normalized schemes also
fail. The exact URI and any surrounding editorial processing instructions remain in the immutable source
artifact. Empty `<idno>` elements do not produce identifiers. TEI v1 and the committed v2 profile retain their
historical identifier projections unchanged; v2's broader URI matching is not silently tightened under
`tei_parser_v2`.

V3 also records each supported direct `<event>` in document order with its required type and optional `when`
and note values. V1 and v2 retain an empty event projection so historical imports remain reproducible. Direct
`<sex>` values are deliberately excluded: existing registers may contain labels produced by an earlier gender
workflow, and passing them to classification methods would leak the target. The exact XML remains preserved;
importing those values later requires a separate annotation or benchmark contract.

## Person-name profiles

`tei_p5_person_register_v1` preserves the historical flat projection: one regular `surname`, ordered regular
`forenames`, and flattened `alt_names`. Its records have `name_forms=None`, which means structured person-name
forms were not captured rather than that the source contained none.

`tei_p5_person_register_v2` additionally records every direct
`<person>/<persName>` in document order. Each `PersonNameForm` preserves `@type`, optional `@subtype`, and either
an unstructured value from direct text or `<name>`, or direct `<surname>` and ordered `<forename>` values. The
parser does not treat nested `<persName>` references inside `<note>`, `<event>`, or other descriptive content as
alternative names. Its committed text and identifier behavior remains frozen.

`tei_p5_person_register_v3` is the default for new imports. It retains v2's structured-name contract while
adding ordered events, strict shared authority normalization, safe visible-text boundaries, and explicit
validation of supported descendant name markup. Callers may still select v1 or v2 explicitly for historical
reproduction.

V2 and v3 continue to populate the flat fields for existing methods, search, and simple tabular exchange. The
first regular form supplies the regular surname and forenames; a regular `<name>` retains the v1 projection
into `surname`. An alternative `<name>` becomes one flat alternative value. For a structured alternative, the
parser joins non-empty surname and forename components with one space. Alternative forenames are not merged
into the regular `forenames` method input.

The structured projection is source-rich but not an XML syntax tree. Empty name components are normalized to
absence, empty `<nameLink/>` placeholders, XML comments, and editorial or Oxygen processing instructions do
not become model fields. V3 inserts a boundary between visible descendant text segments when omitting a
separator would join words, so `van<nameLink/>Helsing` becomes `van Helsing` without adding a space before
punctuation. Corpus-supported inline `<name type="…">` and nested `<persName key="…">` markup becomes
normalized component text; other descendant elements and unsupported attributes are rejected rather than
silently flattened. V1 and v2 retain their historical separator-free descendant concatenation; v2 also
retains its committed descendant-flattening behavior rather than gaining new validation under the same parser
version. The immutable artifact retains the exact syntax.

Structured names participate in v2 and v3 person-input fingerprints in their complete source order. When
`name_forms` is null, fingerprinting retains the v1 projection and omits the new field. Existing ready
snapshots are never reparsed or backfilled; obtaining the current projection from a preserved artifact creates
a new immutable snapshot under v3. See
[ADR-0017](decisions/ADR-0017-structured-tei-person-name-forms.md).

## Supported formats and packaging

Semantic format and delivery packaging remain separate dimensions. Clients declare both; no importer guesses
scientific semantics from an extension or media type.

| Source format | `single` | `loose` | `zip` | `tar_gz` | Import profile |
|---|---:|---:|---:|---:|---|
| TEI XML | yes | yes | yes | yes | `tei_p5_person_register_v1`, `tei_p5_person_register_v2`, or `tei_p5_person_register_v3` |
| CSV | yes | no | no | no | `tei_equivalent_person_register_v1` |
| XLSX | yes | no | no | no | `tei_equivalent_person_register_v1` |
| JSON | yes | no | no | no | `tei_equivalent_person_register_v1` |

A single source contains one document or table. A loose TEI request repeats the multipart file part and uses
each sanitized client filename as its logical member name. ZIP and TAR.GZ retain their exact container bytes
while the worker presents their validated XML members to the same TEI collection importer. Members are ordered
by Unicode-NFC-normalized logical name using a stable case-folded comparison; duplicate `xml:id` values fail
the entire collection, regardless of packaging.

## Archive and collection safety

Loose names and container members must be safe relative POSIX names. Empty names, absolute paths, Windows
drive paths, parent or empty path segments, backslashes, controls, names or basenames that collide after
normalization and case folding, and non-XML regular members are rejected. Archive readers do not extract a
filesystem tree. ZIP encryption, links, unsupported compression, TAR links, sparse files, devices, and other
special members are rejected, as are nested archives.

The accepted SnapshotImportConfig persists independent ceilings for member count, individual expanded bytes,
total expanded bytes, compression ratio, record count, and tabular cell size. Readers enforce archive metadata
before parsing and count actual expanded bytes while reading. These limits complement the request's
compressed-upload bounds, and neither substitutes for the other: `GENDERTAGGER_MAX_ARCHIVE_MEMBER_BYTES`
bounds each individual upload part (100 MiB by default) and `GENDERTAGGER_MAX_SNAPSHOT_UPLOAD_BYTES` bounds
the staged collection as a whole (500 MiB by default, matching the reverse proxy's request-body ceiling in
[12-deployment-and-operations.md](12-deployment-and-operations.md)). Exceeding either returns `413`.

ZIP and XLSX preflight reads bounded classic EOCD or ZIP64 directory metadata before constructing Python ZIP
member objects. It enforces the persisted member-count limit and derives a reproducible central-directory
metadata ceiling as `max(64 KiB, maximum member count × 16 KiB)`; this derived ceiling is not an additional
mutable setting.

## TEI-equivalent tabular profile

CSV, XLSX, and JSON share one exact, hierarchical profile. Its required fields or columns, in CSV/XLSX order,
are:

```text
xml:id,persName,birth,death,event,note,idno
```

`xml:id` is a required non-blank string. `birth`, `death`, and `note` are optional strings. `persName`, `event`,
and `idno` are arrays. JSON supplies those arrays natively in a top-level array of exact person objects. CSV
and XLSX put a JSON array in each corresponding cell. Unknown, missing, duplicate, or reordered CSV/XLSX
columns fail validation; each input record must still contain all seven fields.

A `persName` array preserves its source order and requires exactly one regular form. Each object has
`"type": "reg"` or `"type": "alt"`, may have `subtype`, and uses exactly one representation:

```json
[
  {"type":"reg","surname":"van Helsing","forename":["Abraham","Johannes"]},
  {"type":"alt","subtype":"birthname","name":"Abraham van Helsing"}
]
```

Structured forms require the ordered `forename` array and may supply `surname`; unstructured forms supply
`name`. Multiple forenames and alternative forms therefore retain the same semantics as TEI v3. The importer
derives the compatibility fields `surname`, `forenames`, and `alt_names` from these forms rather than accepting
a second potentially inconsistent representation.

An `event` object requires `type` and may include `when` and `note`. An `idno` object requires `type` and
`value`:

```json
[{"type":"wedding","when":"1817-09-24","note":"Berlin"}]
[{"type":"GND","value":"https://d-nb.info/gnd/118607626"},{"type":"VIAF","value":"12345678"}]
```

Supported GND, VIAF, and Wikidata identifiers and URIs use the same exact-host, canonical-path, conflict, and
duplicate-scheme rules as TEI v3. Typed canonical URIs and typed bare IDs therefore produce the same
authority-local values in every supported format, while spoofed hosts are never inferred. The exact source
values remain available in the immutable source Artifact.

CSV is a fixed comma-delimited UTF-8 format and may start with a UTF-8 BOM. XLSX requires one visible worksheet
named `persons`, the exact header row, and string-valued source cells. Before opening the workbook in read-only
streaming mode, the importer securely parses `[Content_Types].xml`, every relationship part, and every
worksheet part with DTDs, entities, and network access disabled. It rejects macro/dialog/VBA parts and content
types, entity-encoded or plain external relationship modes, formulas, hyperlinks, merged cells, excessive
dimensions or references, populated secondary sheets, unsafe or encrypted ZIP members, and expansion-limit
violations. Rejecting non-string spreadsheet values prevents automatic numeric and date coercion from changing
historical identifiers or life-date text.

JSON decoding rejects integer tokens longer than its fixed safe bound, avoiding interpreter-dependent integer
conversion failures. JSON and CSV string validation rejects U+0000 before persistence. XML 1.0 and XLSX's XML
parts cannot represent that code point, but accepting it from JSON or CSV would otherwise turn a permanent
source error into a PostgreSQL write failure and inappropriate infrastructure retries.

## Snapshot comparison

`person_records` carries a unique `(dataset_snapshot_id, tei_id)` constraint, so `xml:id` identifies exactly
one person inside each snapshot and stays a stable comparison key across a Project's snapshots. Comparison
tooling over that key is not implemented; see [22-future-development.md](22-future-development.md).

## TEI export

`TeiExportProfile` defines one encoding, `tei_p5_gender_v1`, which the export service resolves as the default
for `format='tei'`. It uses a child `<gender>` element on `<person>`, not a shorthand attribute, so the
annotation carries provenance and certainty.

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
- human-reviewed decisions use the configured `human_resp_id`, which defaults to `#editor`
- `@cert` uses TEI values `high`, `low`, `unknown`

The profile inserts the element after the last `<persName>` and therefore before `<birth>`, `<death>`, or
`<note>` children. It parses one member's exact bytes with DTD loading, entity resolution, and network access
disabled, and serializes a new UTF-8 document rather than editing the artifact. A person that carries no
usable decision is left exactly as in the source; a labeled person whose `xml:id` is absent from its member
fails the export.

## TEI certainty projection

The richer internal certainty tier is kept, and the export projects it deterministically to TEI:

- internal `high` -> `high`
- internal `low` -> `low`
- `contested`, `single`, `uncertain`, `no_data` -> `unknown`
- a human-reviewed final decision -> `high`

`TeiExportProfile` is a versioned enum, so a different TEI encoding becomes a new profile value rather than a
change to historical exports.

## Export contract

`POST /exports` takes an `ExportCreateRequest` naming one run and one completed aggregation execution,
persists the export execution and its dispatch intent in the same transaction, and returns `202 Accepted`.
Operators create exports and viewers read them. A selected aggregation that is not exportable returns `409`.

`ExportFormat` defines `tei`, `json`, and `csv`. `LabelSourcePolicy` defines `machine_aggregation`, the
default, and `human_overrides`. Under `human_overrides` a person's current annotation supersedes the machine
label when it carries one, and that override projects at TEI certainty `high`; a `defer` annotation carries no
label, so the aggregated result stands. Under `machine_aggregation` annotations are never consulted. Neither
policy rewrites the underlying Prediction or AggregatedResult. `tei_profile` is accepted only with
`format='tei'`.

The implemented export modes are:

1. TEI with the selected machine aggregation
2. TEI with human overrides and final decisions
3. JSON result bundle, written as `export.json`
4. CSV analysis export, written as `export.csv`
5. an `ExportManifest`, written as `manifest.json` alongside every export

A `tei` export requires a TEI snapshot packaged `single` or `loose`; under that format a tabular snapshot, a
`zip` or `tar_gz` snapshot, or a person record without a source-member locator fails the export terminally
instead of producing partial output. TEI writes one output artifact per source member, named by that member's
logical name and typed `application/tei+xml`. The manifest records the export, snapshot, run, and aggregation
identifiers, the source snapshot SHA-256, the format, the label-source policy, the profile, and one
checksummed descriptor per output. Only a completed export has a manifest artifact, and every completed export
has one.

`GET /exports/{export_id}/download` returns the export's own output bytes and media type when the export
produced exactly one output, which covers every `json` and `csv` export and a `tei` export over a one-member
source. When an export produced several outputs, as a loose TEI collection does, the endpoint returns the
manifest instead, and the individual member outputs are not separately addressable; see
[22-future-development.md](22-future-development.md). An export without a manifest artifact returns `404`.

Never mutate the original source artifact in place.
