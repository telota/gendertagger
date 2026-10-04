# Provenance and reproducibility

## Anonymous name classification

[ADR-0044](decisions/ADR-0044-public-name-classification.md) freezes public job inputs, method descriptors,
validated configuration, and artifact digests before dispatch. Provenance records the application version,
source revision, Python version, exact installed dependency versions, lock digest, and optional image digest.
The worker rejects a changed execution environment rather than recording outputs under stale provenance.
Complete raw method output and normalization metadata remain immutable with completed jobs.
An enabled external LLM also records the operator's immutable model revision. The operator must bind its
model alias to those weights; provenance does not independently attest an external server's weight files.
Public responses expose secret-free scientific configurations, their complete configuration digest,
normalization evidence, and exact environment versions. Immediate responses carry the same provenance
while preserving the synchronous interface's documented non-persistence behavior.

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
- exact installed dependency versions
- start/end timestamps

The Run's snapshot, resolved configuration/hash, code/application/runtime versions, and dependency provenance
are sealed at creation. Only validated lifecycle fields may change afterward.

[ADR-0048](decisions/ADR-0048-project-worker-provenance-compatibility.md) requires project workers to
match that accepted environment and the MethodExecution implementation/normalization before prediction.
New runs capture the installed dependency map; historical runs retain null rather than fabricated
versions and cannot execute on guarded workers without newly accepting the work.

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

Persisted `SnapshotImportConfig` requires explicit source format, packaging, profile, and resolved limits.
Public request defaults remain supported, but acceptance resolves and stores them before dispatch.
Execution never supplies `single` for missing stored packaging or reconstructs missing ready statistics.
Incomplete historical snapshots require a new import from retained source bytes; their metadata and
outputs remain unchanged.

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

The current person-input fingerprint is SHA-256 of canonical JSON for every `PersonInput` field, using
its JSON representation with defaults, nulls, and empty collections included. In particular,
`name_forms: null` and `events: []` are present rather than omitted for older encodings. Ordered names,
forenames, alternative names, and events retain their order; object key order does not affect the hash.
Persistence identity, snapshot ID, source-member/record locators, and creation time are not method input
and do not participate.

The accepted Run source revision and matching worker provenance identify this fingerprint contract;
there is no new persisted version field or historical-hash compatibility path. Existing Predictions
retain their original fingerprint and are interpreted under their recorded environment, not recalculated
using current code. New Runs use the current contract; reimport only snapshots with incomplete import
provenance or statistics. Scientific labels, normalization, aggregation, certainty, TEI output semantics,
and evaluation definitions are unchanged. See
[ADR-0049](decisions/ADR-0049-current-person-input-fingerprints-and-snapshot-metadata.md).

## TaskBatch execution provenance

An atomic claim records a canonical `WorkerProvenance` with the worker's actual hostname, process ID,
source/application/Python versions, dependency-lock digest, exact installed dependencies, and optional
image digest. That receipt is immutable after claim and stays internal; MethodExecution's already sealed
metadata is not repurposed as mutable worker state. Duplicate delivery cannot replace a receipt or output.
Transient rollback removes the claim and receipt; the completing attempt supplies the final receipt.

Before invoking an adapter, compare its persisted implementation/normalization and every accepted Run
environment field with the worker. Validate the persisted configuration digest and pinned asset bytes,
including model-manifest membership and the materialized files consumed by the model. An incompatible
worker records a permanent `IncompatibleWorkerError` with no Predictions. Restore the matching environment
for unclaimed work, or accept a new Run; terminal failed batches are never reopened and accepted scientific
provenance is never rewritten. External LLM model identity remains operator-declared, not independent
attestation of a server's weights. See [ADR-0048](decisions/ADR-0048-project-worker-provenance-compatibility.md).


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
([`models/export.py`](../backend/src/gendertagger/models/export.py), assembled by
[`export/manifest.py`](../backend/src/gendertagger/export/manifest.py)) alongside its output artifacts:

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

## Configuration hashes

Runs, method executions, aggregations, and evaluations store a `config_sha256` over their canonical resolved
configuration: a compact fingerprint for comparing provenance, and for aggregations also the creation identity
that [ADR-0034](decisions/ADR-0034-reuse-matching-aggregation-on-creation.md) matches on. Dataset snapshots
and exports deliberately have none. A snapshot's import is already identified exactly by `source_sha256`,
`parser_version`, and the persisted `import_config`; an export's configuration is four plain columns
(`format`, `label_source_policy`, `tei_profile`, `human_resp_id`). Add a hash only when a feature consumes it,
for example deduplicating identical export requests.

## Reproducibility level

Aim for "recreate the scientific computation from captured inputs/configuration", not bit-for-bit equality across every GPU/library environment. Record enough runtime information to diagnose differences.
