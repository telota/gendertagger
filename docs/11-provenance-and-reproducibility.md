# Provenance and reproducibility

## Goal

A result should answer: **what input, code, configuration, method/model/data revision, and decision process produced this label?**

## Run provenance

Persist at least:

- run ID
- DatasetSnapshot ID and source hash
- resolved RunConfig and hash
- code Git commit
- application version
- container image digest when containerized
- Python/runtime version
- dependency lockfile/artifact reference
- start/end timestamps

## DatasetSnapshot import provenance

Persist enough information to re-run the exact importer over the exact accepted source collection:

- source format, packaging, and versioned import profile;
- importer implementation version;
- primary Artifact checksum and reference;
- deterministic source manifest where packaging is `loose`;
- each staged upload member's ordinal, safe logical name, Artifact reference, checksum, byte size, and media
  type;
- resolved member-count, expansion, compression-ratio, record-count, and tabular-cell limits;
- each PersonRecord's source-member name and source-record locator;
- ready record count or sanitized terminal failure.

The source hash alone is not a substitute for the member manifest or import config. Conversely, source-member
metadata is not a substitute for retaining the exact single file, archive, workbook, table, or loose member
bytes. A change to deployment defaults does not reinterpret an already accepted pending snapshot.

## MethodExecution provenance

Persist:

- stable method identifier
- adapter implementation version
- resolved method config and hash
- model identifier/revision/checksum where applicable
- local dataset/dictionary artifact checksum/date
- prompt/schema version for LLMs
- queue/resource class
- worker/runtime metadata

For the reference study this includes, where applicable, local GND/HIVOTO snapshots, transformer model identifiers/revisions, NQG threshold, XGBoost training/model artifact details, and local LLM prompt/schema/model tag.

## Prediction provenance

Persist:

- person input fingerprint
- normalized label/status
- method_confidence
- raw label/output
- normalization version and outcome reason
- cache provenance if reused

## Aggregation provenance

Persist:

- strategy ID/version
- exact MethodExecution IDs included
- strategy config/hash
- decision outcome, canonical label, and any tied labels
- override source plus agreeing/comparison counts
- complete pooled vote counts
- agreement score/tier
- certainty tier

## Annotation provenance

Persist reviewer and referenced machine result. Export responsibility must reflect whether the final decision is automated or human-reviewed.

## Export manifest

Every export should have a machine-readable manifest containing:

- source snapshot hash
- selected run/aggregation
- human-override policy
- export profile/version
- output checksum
- timestamp

## Reproducibility level

Aim for "recreate the scientific computation from captured inputs/configuration", not bit-for-bit equality across every GPU/library environment. Record enough runtime information to diagnose differences.
