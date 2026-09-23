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

The Run's snapshot, resolved configuration/hash, code/application/runtime versions, and dependency provenance
are sealed at creation. Only validated lifecycle fields may change afterward.

## DatasetSnapshot import provenance

Persist enough information to re-run the exact importer over the exact accepted source collection:

- source format, packaging, and the derived import profile;
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

The owning Run and all scientific method/configuration/model/data/prompt/schema provenance, including captured
worker metadata, are sealed at creation. Progress, timestamps, and sanitized failure details remain operational
lifecycle fields only while execution is active. PostgreSQL rejects changes outside that allowlist and seals
the entire row once it reaches a terminal state.

For the reference study this includes, where applicable, local GND/HIVOTO snapshots, transformer model identifiers/revisions, NQG threshold, XGBoost training/model artifact details, and local LLM prompt/schema/model tag.

For table-backed methods, retain both the original source artifact(s) and the compiled lookup artifact. The
resolved method configuration identifies the compiled artifact by `lookup_sha256`, and
`MethodExecution.data_artifact_id` references those exact consumed bytes. Artifact metadata links the compiled
lookup to every source artifact/checksum, the source release, compiler version, lookup-schema version, and
applicable license or access restrictions. PostgreSQL stores this metadata, not the full
GND/Wiki-Gendersort/HIVOTO lookup rows.


## Prediction provenance

Persist:

- required TaskBatch ID
- person input fingerprint
- normalized label/status
- method_confidence
- raw label/output
- normalization version and outcome reason
- cache provenance if reused

A Prediction may be created only for the exact person slice of its running TaskBatch while the owning
MethodExecution and Run are also running. Its creation and TaskBatch completion share one transaction. The
row is immutable afterward, so its method and batch provenance cannot be detached from the output.

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

The aggregation's owning Run, strategy, resolved configuration/hash, and exact ordered MethodExecution
membership are sealed before execution. Results may be created only while that aggregation is running, must
exactly cover its Run snapshot, and are committed atomically with aggregation completion. Both membership and
result rows are immutable after sealing/creation.

## Annotation provenance

Persist reviewer and referenced machine result. Export responsibility reflects whether the final
decision is automated or human-reviewed: `ExportExecution.label_source_policy` selects between
`machine_aggregation` and `human_overrides`, and `human_resp_id` records the responsible editor
reference projected into TEI output.

## Export manifest

Every export persists a machine-readable `ExportManifest`
([`models/export.py`](../src/gendertagger/models/export.py), assembled by
[`export/manifest.py`](../src/gendertagger/export/manifest.py)) alongside its output artifacts:

- `version`, the manifest format version (currently `1`); any change to the persisted fields requires a new
  version, as for the source manifest
- `export_execution_id`
- `dataset_snapshot_id` and `source_snapshot_sha256`
- `run_id` and `aggregation_execution_id`
- `format` and, for TEI, `tei_profile`
- `label_source_policy`
- `outputs`, one or more `ExportManifestOutput` entries carrying `logical_name`, `sha256`,
  `byte_size`, and `media_type`
- `generated_at`

## Reproducibility level

Aim for "recreate the scientific computation from captured inputs/configuration", not bit-for-bit equality across every GPU/library environment. Record enough runtime information to diagnose differences.
