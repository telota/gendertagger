# Pydantic contracts

## Principle

Pydantic is the canonical language for typed contracts across the application. These are **not**
SQLAlchemy models.

The same conceptual models are reused by:

- FastAPI request/response schemas
- application services
- method adapters
- aggregation
- import/export
- configuration loading
- Celery task envelopes
- CLI
- tests

Separate Create/Read/Command models exist wherever mutability or security boundaries differ.

## Contract modules

Every canonical contract lives under `src/gendertagger/models/`, except the run-configuration
envelope in `src/gendertagger/config/run.py`. Every contract model sets `extra="forbid"`, and the
read, command, and message models are additionally frozen.

| Module | Contract family |
| --- | --- |
| `config/run.py` | `AggregationStrategy`, `MethodRunConfig`, `AggregationConfig`, `ExecutionConfig`, `RunConfig`, YAML loading |
| `models/classification.py` | `CanonicalLabel`, `PredictionStatus`, `CertaintyTier`, `AgreementTier`, `LlmSelfReportedCertainty`, `PredictionResult` |
| `models/lifecycle.py` | Status enums for snapshots, runs, method executions, aggregations, evaluations, exports, and task batches |
| `models/person.py` | `PersonNameType`, `PersonNameForm`, `PersonEvent`, `PersonInput`, `ImportedPerson`, `PersonRecord` |
| `models/project.py` | Project, dataset-snapshot, source-manifest, and snapshot-import contracts |
| `models/method.py` | `MethodConfidenceRange`, `MethodDescriptor`, `METHOD_NAME_PATTERN` |
| `models/run.py` | `Progress`, run, method-execution, task-batch, prediction, and SSE-event contracts |
| `models/aggregation.py` | Reference-aggregation decision, result, and execution contracts |
| `models/evaluation.py` | Evaluation definition, execution, and report contracts |
| `models/export.py` | Export command, execution, projection, and manifest contracts |
| `models/review.py` | Annotation, review-state, and review-queue contracts |
| `models/dispatch.py` | Durable task-dispatch outbox contracts |
| `models/artifact.py` | Artifact records plus compiled-lookup and model-manifest metadata |
| `models/classify.py` | Synchronous on-demand classification request and response |
| `models/api.py` | `ApiErrorDetail`, `ApiErrorEnvelope`, `CursorPage` |
| `models/user.py` | `Role`, `CurrentUser`, `UserCreate`, `User` |
| `models/common.py` | `UtcDatetime`, `canonical_json_sha256` |
| `models/queues.py` | Operational queue-routing vocabulary |

## Core enums

`src/gendertagger/models/classification.py` defines the shared classification vocabulary as
`StrEnum` members, so each value serializes as its stable lowercase string:

```python
class CanonicalLabel(StrEnum):
    male = "male"
    female = "female"
    unknown = "unknown"
    institution = "institution"


class PredictionStatus(StrEnum):
    success = "success"
    abstain = "abstain"
    error = "error"


class CertaintyTier(StrEnum):
    high = "high"
    low = "low"
    contested = "contested"
    single = "single"
    uncertain = "uncertain"
    no_data = "no_data"


class AgreementTier(StrEnum):
    unanimous = "unanimous"
    strong_majority = "strong_majority"
    weak_majority = "weak_majority"
    no_consensus = "no_consensus"
    single_rater = "single_rater"
    no_answer = "no_answer"


class LlmSelfReportedCertainty(StrEnum):
    high = "high"
    low = "low"
    uncertain = "uncertain"
```

## Lifecycle status enums

`src/gendertagger/models/lifecycle.py` defines one `StrEnum` per persisted lifecycle. Runs and
method executions carry the additional `completed_with_errors` state; the aggregation, evaluation,
export, and task-batch lifecycles do not.

| Enum | Values |
| --- | --- |
| `DatasetSnapshotStatus` | `pending`, `importing`, `ready`, `failed` |
| `RunStatus` | `created`, `queued`, `running`, `completed`, `completed_with_errors`, `failed`, `cancelled` |
| `MethodExecutionStatus` | `pending`, `queued`, `running`, `completed`, `completed_with_errors`, `failed`, `cancelled` |
| `AggregationExecutionStatus` | `pending`, `queued`, `running`, `completed`, `failed`, `cancelled` |
| `EvaluationExecutionStatus` | `pending`, `queued`, `running`, `completed`, `failed`, `cancelled` |
| `ExportExecutionStatus` | `pending`, `queued`, `running`, `completed`, `failed`, `cancelled` |
| `TaskBatchStatus` | `pending`, `queued`, `running`, `completed`, `failed`, `cancelled` |

## Person input contract

```python
class PersonNameType(StrEnum):
    regular = "reg"
    alternative = "alt"


class PersonNameForm(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: PersonNameType
    subtype: str | None = Field(default=None, max_length=100)
    name: str | None = None
    surname: str | None = None
    forenames: list[str] = Field(default_factory=list)


class PersonEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str = Field(min_length=1, max_length=100)
    when: str | None = None
    note: str | None = None


class PersonInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tei_id: str = Field(min_length=1)
    surname: str | None = None
    forenames: list[str] = Field(default_factory=list)
    birth: str | None = None
    death: str | None = None
    note: str | None = None
    events: list[PersonEvent] = Field(default_factory=list)
    alt_names: list[str] = Field(default_factory=list)
    name_forms: list[PersonNameForm] | None = None
    gnd_id: str | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)
```

Do not over-normalize historical values on ingestion. Preserve source strings and add normalized helper fields
only where necessary.
`tei_id` is required and must not be empty or contain only whitespace; validation does not trim or otherwise
normalize the source identifier.

`surname`, `forenames`, and `alt_names` remain the stable flat classification, search, and tabular
projections. `name_forms` is an additive source-rich representation of direct TEI
`<person>/<persName>` children in document order. Each `PersonNameForm` preserves the TEI `type`,
optional source `subtype`, and exactly one name representation: either an unstructured value from
direct text or `<name>`, or the structured surname and ordered forenames. A form validator rejects
any name form that supplies both or neither. Nested `<persName>` references inside notes or events
are not included. The contract rejects unknown fields; import profiles define which TEI structures
they support.

`name_forms=None` is a provenance value: it means the legacy parser profile did not capture the
structured forms. A populated list means the selected profile did examine them; the v2 and v3
contracts require exactly one regular form. Both structured-name parsers derive the flat fields
deterministically from this ordered list, and `PersonInput` validates that agreement: `surname`
matches the regular form's surname or unstructured name, `forenames` matches its ordered forenames,
and `alt_names` matches the alternative forms projected through `PersonNameForm.projected_text()`.
Legacy inputs may continue to supply only the flat fields. Alternative forenames are not added to
regular `forenames` automatically. See
[ADR-0017](decisions/ADR-0017-structured-tei-person-name-forms.md).

`events` preserves ordered biographical events as a type plus optional source `when` and note
strings. TEI v3 and the tabular profile populate it; TEI v1 and v2 retain an empty list for
historical reproducibility. Direct source `<sex>` values are intentionally not PersonInput fields
because existing values may be earlier classification targets. See
[`22-future-development.md`](22-future-development.md) for how a label-bearing importer would
handle them.

Person-input fingerprints preserve this profile distinction. `_person_input_fingerprint` in
`src/gendertagger/services/execution.py` dumps only the `PersonInput` field projection and hashes it
with `canonical_json_sha256`. A null `name_forms` value drops the key entirely and so keeps the v1
fingerprint. A populated list uses the structured projection introduced in v2 and includes the
complete ordered value. A non-empty `events` list likewise participates in order, while an empty
list is omitted to retain fingerprints created before event projection existed. This makes source
structure reproducible without changing historical v1 or v2 fingerprints.

An imported projection carries record-level source provenance before persistence, and the persisted
read model carries the same provenance plus snapshot identity:

```python
class ImportedPerson(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    person: PersonInput
    source_member_name: str = Field(min_length=1, max_length=SOURCE_MEMBER_LOGICAL_NAME_MAX_LENGTH)
    source_record_locator: str = Field(min_length=1)


class PersonRecord(PersonInput):
    id: UUID
    dataset_snapshot_id: UUID
    source_member_name: str
    source_record_locator: str
    created_at: UtcDatetime
```

The member name identifies the exact loose file, container member, or single source artifact, and is
normalized through the shared `normalize_source_member_logical_name` safety rules. The locator is
format-specific, such as an encoded XML ID selector or a tabular row. Both values are strictly
required and persisted together on PersonRecords.

## Snapshot import contracts

Format, delivery packaging, and record mapping are independent, explicit choices:

```python
class SourceFormat(StrEnum):
    tei = "tei"
    csv = "csv"
    xlsx = "xlsx"
    json = "json"


class SourcePackaging(StrEnum):
    single = "single"
    loose = "loose"
    zip = "zip"
    tar_gz = "tar_gz"


class TeiImportProfile(StrEnum):
    tei_p5_person_register_v1 = "tei_p5_person_register_v1"
    tei_p5_person_register_v2 = "tei_p5_person_register_v2"
    tei_p5_person_register_v3 = "tei_p5_person_register_v3"


class TabularImportProfile(StrEnum):
    tei_equivalent_person_register_v1 = "tei_equivalent_person_register_v1"


ImportProfile = TeiImportProfile | TabularImportProfile

DEFAULT_TEI_IMPORT_PROFILE = TeiImportProfile.tei_p5_person_register_v3
DEFAULT_SOURCE_FORMAT = SourceFormat.tei
DEFAULT_SOURCE_PACKAGING = SourcePackaging.single


class SnapshotImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_format: SourceFormat = DEFAULT_SOURCE_FORMAT
    packaging: SourcePackaging = DEFAULT_SOURCE_PACKAGING
    profile: ImportProfile = DEFAULT_TEI_IMPORT_PROFILE
```

The supported matrix is TEI with `single`, `loose`, `zip`, or `tar_gz` packaging and CSV, XLSX, or
JSON with `single` packaging. Profile validation rejects incompatible combinations rather than
inferring them from an extension or client media type. New requests default to single-file TEI v3;
v1 and the committed v2 profile remain explicitly selectable for reproducible imports.

`SnapshotImportConfig` extends the request with the resolved immutable `SnapshotImportLimits`:

```python
class SnapshotImportLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_member_count: int = Field(default=128, gt=0)
    max_member_expanded_bytes: int = Field(default=100 * 1024 * 1024, gt=0)
    max_total_expanded_bytes: int = Field(default=500 * 1024 * 1024, gt=0)
    max_compression_ratio: float = Field(default=100.0, gt=1.0, allow_inf_nan=False)
    max_record_count: int = Field(default=1_000_000, gt=0)
    max_cell_bytes: int = Field(default=1024 * 1024, gt=0)


class SnapshotImportConfig(SnapshotImportRequest):
    limits: SnapshotImportLimits
```

The complete config is stored in `DatasetSnapshotCreate.import_config` on the pending snapshot, so
the worker applies the limits accepted with that command even if deployment settings later change.

Loose collections use a frozen `SourceManifestV1` containing `version`, format, packaging, and one
or more ordered `SourceManifestMember` values. Each member has a safe logical name, SHA-256
checksum, byte size, and canonical media type. `SourceManifestV1.canonical_bytes()` returns compact
UTF-8 JSON with sorted object keys, and those bytes are the aggregate source artifact. Persisted
`SnapshotSourceMember` values additionally carry the exact Artifact ID and contiguous ordinal for
all packaging modes. See
[ADR-0021](decisions/ADR-0021-versioned-multi-format-snapshot-ingestion.md).

## Prediction result contract

```python
class PredictionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: CanonicalLabel | None
    status: PredictionStatus
    method_confidence: float | None = Field(default=None, allow_inf_nan=False)
    raw_label: str | None = None
    raw_output: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Validation invariants:

- `status=success` requires a canonical `label`.
- `status in {abstain,error}` requires `label=None`.
- `method_confidence`, if present, must be finite and in the method's declared range; the adapter boundary
  enforces the declared range. `[0,1]` is preferred but not assumed globally unless the adapter declares it.

`PredictionWrite` and the `Prediction` read model in `src/gendertagger/models/run.py` bind one
result to its person record, task batch, and SHA-256 `input_fingerprint`.

## Method contract

Method implementations live in code and register a stable lowercase snake-case method identifier
matching `METHOD_NAME_PATTERN` (`^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$`). Runtime configuration is YAML
parsed through Pydantic. A frozen `MethodDescriptor` in `src/gendertagger/models/method.py` carries
only the scientific provenance needed at the adapter boundary:

```python
class MethodConfidenceRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum: float = Field(allow_inf_nan=False)
    maximum: float = Field(allow_inf_nan=False)


class MethodDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=METHOD_NAME_PATTERN)
    implementation_version: str = Field(min_length=1)
    normalization_version: str = Field(min_length=1)
    method_confidence_range: MethodConfidenceRange | None = None
```

Both bounds are finite and `minimum` must be strictly less than `maximum`. Operational routing, UI
display metadata, and reference-aggregation membership are separate concerns and do not belong in
this descriptor; `MethodRegistration` in `src/gendertagger/services/method_registry.py` holds the
queue name, batch size, and asset logical types instead.

Every adapter exposes its concrete Pydantic `config_model`, derived from the closed `MethodConfig`
base in `src/gendertagger/methods/base.py`. Lookup-backed adapters use `LookupMethodConfig`, which
selects a compiled SQLite artifact by its `lookup_sha256` digest. `MethodRegistry.resolve_run_config`
applies defaults and validates raw configuration through that model before the typed, batch-first
interface is invoked:

```python
MethodConfigT = TypeVar("MethodConfigT", bound=MethodConfig)


class GenderMethod(Protocol[MethodConfigT]):
    descriptor: MethodDescriptor
    config_model: type[MethodConfigT]

    def predict_batch(
        self,
        people: Sequence[PersonInput],
        config: MethodConfigT,
    ) -> list[PredictionResult]: ...
```

The returned list contains exactly one result per input in the same order. Record-specific scientific or
input failures are returned with `status=error`; batch-wide infrastructure failures and invalid adapter or
configuration state raise so orchestration can apply retry policy. `validate_prediction_batch` is the
adapter boundary: it checks result cardinality, rejects a reported confidence when the descriptor
declares no range, and rejects any value outside the inclusive declared `method_confidence_range`,
raising `MethodContractError`. A missing extra, model, or authority snapshot raises
`MethodDependencyError`, which orchestration treats as a permanent rather than a retryable failure.

Batch-first design avoids a task per person while allowing adapters to use vectorized/GPU inference.

## Reference aggregation decision

The pure `reference_v1` priority and voting step returns an immutable decision before agreement and certainty
are derived:

```python
class AggregationOutcome(StrEnum):
    decided = "decided"
    unresolved_tie = "unresolved_tie"
    no_data = "no_data"


class OverrideSource(StrEnum):
    parenthetical_qualifier = "parenthetical_qualifier"
    gnd = "gnd"


class VoteCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    male: int = Field(default=0, ge=0)
    female: int = Field(default=0, ge=0)
    unknown: int = Field(default=0, ge=0)
    institution: int = Field(default=0, ge=0)


class ReferenceAggregationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: AggregationOutcome
    label: CanonicalLabel | None
    pooled_vote_counts: VoteCounts = Field(default_factory=VoteCounts)
    tied_labels: tuple[CanonicalLabel, ...] = ()
    override_source: OverrideSource | None = None
    override_agreeing_count: int | None = Field(default=None, ge=0)
    override_comparison_count: int | None = Field(default=None, ge=0)


class ReferenceAggregationResult(ReferenceAggregationDecision):
    agreement_score: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    agreement_tier: AgreementTier
    certainty_tier: CertaintyTier
```

A decided result has one label. An unresolved substantive tie and a no-data result have `label=None`; they
remain distinct through `outcome`, and a tie also carries deterministic `tied_labels`. Vote counts always use
the fixed four-label shape, and `VoteCounts` exposes `total` and `for_label()` helpers. Override
decisions carry both agreeing and comparison counts so agreement can be derived without re-reading
Predictions. The final result adds the versioned agreement score/tier and certainty
tier. A lone local-LLM vote must carry a valid `LlmSelfReportedCertainty` value in
`metadata.self_reported_certainty`; its numeric `method_confidence` is not used for certainty.

The model validators enforce the edge contract directly: a no-data outcome must have no pooled
votes, an unresolved tie needs at least two distinct tied labels and non-zero pooled votes, only a
decided outcome may name an override source, override support counts are present together with
`agreeing <= comparison`, a no-data result must pair `AgreementTier.no_answer` with
`CertaintyTier.no_data` and no agreement score, an unresolved tie must pair
`AgreementTier.no_consensus` with `CertaintyTier.contested`, and an override requires
`CertaintyTier.high`.

## Aggregation execution contracts

An aggregation is an independently rerunnable resource over an exact method-execution selection:

```python
class AggregationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: AggregationStrategy = AggregationStrategy.reference_v1
    method_execution_ids: tuple[UUID, ...] = Field(min_length=1)


class AggregationExecutionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    strategy: AggregationStrategy = AggregationStrategy.reference_v1
    resolved_config: dict[str, JsonValue] = Field(default_factory=dict)
    method_execution_ids: tuple[UUID, ...] = Field(min_length=1)


class AggregationExecution(AggregationExecutionCreate):
    id: UUID
    config_sha256: str = Field(pattern=SHA256_PATTERN)
    status: AggregationExecutionStatus
    started_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None
    failure_class: str | None = None
    failure_diagnostic: str | None = None
    created_at: UtcDatetime
```

`method_execution_ids` rejects duplicates. `canonical_config_sha256()` hashes the versioned strategy
together with its resolved configuration, so a rerun with identical inputs is recognizable.
The lifecycle validator requires `finished_at` on terminal statuses, `started_at` once running or
completed, and a failure diagnostic exactly when the status is `failed`.

Per-person output uses `AggregationResultWrite` before persistence and the `AggregatedResult` read
model afterwards. Both extend `ReferenceAggregationResult` with `person_record_id`, a projected
`has_prediction_error` flag, and free-form `metadata`; `AggregatedResult` adds `id`,
`aggregation_execution_id`, and `created_at`. `AggregationPersonPredictions` carries the present
method outputs for one person as a `dict[str, PredictionResult]`, so an absent required method
stays distinguishable from an explicit `abstain` or `error`.

## Run configuration

A YAML file is input, but the **resolved Pydantic object** is authoritative for a run and is persisted with
a canonical JSON representation and hash. Parsing performs structural envelope validation: the central
wrapper validates stable method identifiers and JSON-compatible configuration values. Before creating a Run,
the server-side method registry must validate every method name, apply adapter-specific defaults, and validate
each nested method configuration against its adapter contract. Only that fully resolved result is persisted
and hashed.

```python
class AggregationStrategy(StrEnum):
    reference_v1 = "reference_v1"


class MethodRunConfig(BaseModel):
    name: str
    enabled: bool = True
    config: dict[str, JsonValue] = Field(default_factory=dict)


class AggregationConfig(BaseModel):
    strategy: AggregationStrategy = AggregationStrategy.reference_v1


class ExecutionConfig(BaseModel):
    fail_run_on_optional_method_error: bool = False


class RunConfig(BaseModel):
    methods: list[MethodRunConfig]
    aggregation: AggregationConfig = Field(default_factory=AggregationConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
```

Every configuration model rejects unknown fields. Method identifiers are lowercase snake case and unique
within a run, including disabled methods. Configuration mappings contain finite JSON values only. YAML is
loaded with safe standard-tag construction, and duplicate mapping keys are rejected.

Canonical JSON is the resolved model dump, including defaults and nulls, encoded with sorted object keys,
compact separators, unescaped Unicode, and no non-finite numbers. Its provenance hash is the lowercase
SHA-256 digest of those UTF-8 JSON bytes. Object-key order, comments, and omitted-versus-explicit defaults do
not affect the hash; list order remains significant.

No service should read arbitrary YAML after a Run has been created. Workers consume the persisted resolved
configuration.

## Celery task envelopes

Use small Pydantic envelopes:

```python
class TaskBatchMessage(BaseModel):
    method_execution_id: UUID
    task_batch_id: UUID


class AggregationTaskMessage(BaseModel):
    aggregation_execution_id: UUID


class SnapshotImportTaskMessage(BaseModel):
    dataset_snapshot_id: UUID
```

Workers load authoritative state from PostgreSQL. Do not serialize PersonInput objects, Predictions, or
aggregation result data into Redis. A snapshot-import worker also resolves its Artifact, import configuration,
and parser version from the persisted DatasetSnapshot; its message contains no upload bytes, filename,
temporary path, storage URI, or parser configuration.

The durable outbox contract is generic but typed. Its target kind is `task_batch`, `aggregation_execution`, or
`dataset_snapshot`; its matching owner ID is unique, and its payload validates as the corresponding message
model. Exactly one typed owner is present. A closed publisher mapping derives the Celery task name; queue,
target kind, owner, payload, and derived task name cannot disagree. See
[ADR-0016](decisions/ADR-0016-asynchronous-aggregation-outbox.md) and
[ADR-0020](decisions/ADR-0020-asynchronous-snapshot-import-outbox.md).


## Browser/API support contracts

Frontend transport contracts remain Pydantic models and therefore appear in OpenAPI. Do not create a parallel set of handwritten TypeScript domain definitions.

### Progress

```python
class Progress(BaseModel):
    total: int | None = Field(default=None, ge=0)
    completed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    percentage: float | None = Field(default=None, ge=0, le=100)
```

Run and MethodExecution read models expose progress without exposing Celery state.

The method-execution contract is split along that boundary. `MethodExecutionSummary` is the public read model
returned by `/api/v1`; `MethodExecution` extends it with the internal `queue_name` and `worker_metadata`
routing and worker-provenance fields consumed by services, repositories, and workers. Endpoints declare the
summary as their response model, so queue names and worker identities reach neither the JSON payload nor the
generated OpenAPI document.

### Cursor pages

```python
T = TypeVar("T")


class CursorPage(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool
```

Use summary response models for list views and detail response models for large/raw scientific output.

### Current user

```python
class Role(StrEnum):
    viewer = "viewer"
    reviewer = "reviewer"
    operator = "operator"
    admin = "admin"
```

Roles are persisted independently of the concrete authentication provider.

```python
class CurrentUser(BaseModel):
    id: UUID
    display_name: str
    roles: set[Role]
```

The exact identity provider is infrastructure. Phase 3 exposes global roles only; project-scoped permissions remain deferred until their semantics are defined. Services consume this explicit authenticated principal.

### Review concurrency
```python
class ReviewAction(StrEnum):
    verify = "verify"
    correct = "correct"
    defer = "defer"


class ReviewWorkflowState(StrEnum):
    unreviewed = "unreviewed"
    reviewed = "reviewed"
    deferred = "deferred"
```

`verify` and `correct` record an explicit canonical label. `defer` records no label and leaves the item in
the deferred workflow state.


```python
class AnnotationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: UUID
    tei_id: str = Field(min_length=1)
    action: ReviewAction
    label: CanonicalLabel | None = None
    comment: str | None = None
    aggregated_result_id: UUID | None = None
    expected_revision: int = Field(ge=0)
```

The command appends a new Annotation when `expected_revision` matches the current review stream. It never updates an existing annotation in place.

```python
class ReviewState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: UUID
    person_record_id: UUID
    tei_id: str
    revision: int = Field(ge=0)
    workflow_state: ReviewWorkflowState
    current_annotation_id: UUID | None = None
```

`ReviewState` is a workflow/concurrency projection. Annotation history remains the scholarly record.

### API errors

```python
class ApiErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ApiErrorEnvelope(BaseModel):
    error: ApiErrorDetail
```

Error codes are stable client-facing values even when internal exception classes change.

## Serialization contract

Public `/api/v1` serialization uses `snake_case`, stable lowercase enum strings, UUID strings, and timezone-aware ISO 8601 timestamps. `null` means absence; it must never stand in for the substantive canonical label `unknown`.
