# Pydantic contracts

## Principle

Pydantic is the canonical language for typed contracts across the application. These are **not** SQLAlchemy models.

The same conceptual models should be reusable by:

- FastAPI request/response schemas
- application services
- method adapters
- aggregation
- import/export
- configuration loading
- Celery task envelopes
- CLI
- tests

Use separate Create/Read/Command models where mutability or security boundaries differ.

## Core enums

```python
class CanonicalLabel(str, Enum):
    male = "male"
    female = "female"
    unknown = "unknown"
    institution = "institution"


class PredictionStatus(str, Enum):
    success = "success"
    abstain = "abstain"
    error = "error"


class CertaintyTier(str, Enum):
    high = "high"
    low = "low"
    contested = "contested"
    single = "single"
    uncertain = "uncertain"
    no_data = "no_data"


class AgreementTier(str, Enum):
    unanimous = "unanimous"
    strong_majority = "strong_majority"
    weak_majority = "weak_majority"
    no_consensus = "no_consensus"
    single_rater = "single_rater"
    no_answer = "no_answer"


class LlmSelfReportedCertainty(str, Enum):
    high = "high"
    low = "low"
    uncertain = "uncertain"
```

## Person input contract

```python
class PersonInput(BaseModel):
    tei_id: str = Field(min_length=1)
    surname: str | None = None
    forenames: list[str] = Field(default_factory=list)
    birth: str | None = None
    death: str | None = None
    note: str | None = None
    alt_names: list[str] = Field(default_factory=list)
    gnd_id: str | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)
```

Do not over-normalize historical values on ingestion. Preserve source strings and add normalized helper fields only where necessary.
`tei_id` is required and must not be empty or contain only whitespace; validation does not trim or otherwise
normalize the source identifier.

## Prediction result contract

```python
class PredictionResult(BaseModel):
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

## Method contract

Method implementations live in code and register a stable lowercase snake-case method identifier. Runtime
configuration is YAML parsed through Pydantic. A frozen `MethodDescriptor` carries only scientific provenance
needed at the adapter boundary:

```python
class MethodConfidenceRange(BaseModel):
    minimum: float
    maximum: float


class MethodDescriptor(BaseModel):
    name: str
    implementation_version: str
    normalization_version: str
    method_confidence_range: MethodConfidenceRange | None = None
```

Operational routing, UI display metadata, and reference-aggregation membership are separate concerns and do
not belong in this descriptor.

Every adapter exposes its concrete Pydantic `config_model`. The server-side registry applies defaults and
validates raw configuration through that model before invoking the typed, batch-first interface:

```python
MethodConfigT = TypeVar("MethodConfigT", bound=MethodConfig)


class GenderMethod(Protocol[MethodConfigT]):
    descriptor: MethodDescriptor
    config_model: type[MethodConfigT]

    def predict_batch(
        self,
        people: list[PersonInput],
        config: MethodConfigT,
    ) -> list[PredictionResult]: ...
```

The returned list contains exactly one result per input in the same order. Record-specific scientific or
input failures are returned with `status=error`; batch-wide infrastructure failures and invalid adapter or
configuration state raise so orchestration can apply retry policy. The adapter boundary validates result
cardinality and any reported value against the inclusive declared `method_confidence_range`.

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
    male: int = 0
    female: int = 0
    unknown: int = 0
    institution: int = 0


class ReferenceAggregationDecision(BaseModel):
    outcome: AggregationOutcome
    label: CanonicalLabel | None
    pooled_vote_counts: VoteCounts
    tied_labels: tuple[CanonicalLabel, ...] = ()
    override_source: OverrideSource | None = None
    override_agreeing_count: int | None = None
    override_comparison_count: int | None = None


class ReferenceAggregationResult(ReferenceAggregationDecision):
    agreement_score: float | None
    agreement_tier: AgreementTier
    certainty_tier: CertaintyTier
```

A decided result has one label. An unresolved substantive tie and a no-data result have `label=None`; they
remain distinct through `outcome`, and a tie also carries deterministic `tied_labels`. Vote counts always use
the fixed four-label shape. Override decisions carry both agreeing and comparison counts so agreement can be
derived without re-reading Predictions. The final result adds the versioned agreement score/tier and certainty
tier. A lone local-LLM vote must carry a valid `LlmSelfReportedCertainty` value in
`metadata.self_reported_certainty`; its numeric `method_confidence` is not used for certainty.

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
```

Workers load authoritative state from PostgreSQL. Do not serialize PersonInput objects, Predictions, or
aggregation result data into Redis.

The durable outbox contract is generic but typed. Its target kind is `task_batch` or
`aggregation_execution`; its matching owner ID is unique, and its payload validates as the corresponding
message model. Exactly one typed owner is present. A closed publisher mapping derives the Celery task name;
queue, target kind, owner, payload, and derived task name cannot disagree. See
[ADR-0016](decisions/ADR-0016-asynchronous-aggregation-outbox.md).


## Browser/API support contracts

Frontend transport contracts remain Pydantic models and therefore appear in OpenAPI. Do not create a parallel set of handwritten TypeScript domain definitions.

### Progress

```python
class Progress(BaseModel):
    total: int | None = None
    completed: int = 0
    failed: int = 0
    percentage: float | None = None
```

Run and MethodExecution read models expose progress without exposing Celery state.

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
    snapshot_id: UUID
    tei_id: str
    action: ReviewAction
    label: CanonicalLabel | None = None
    comment: str | None = None
    expected_revision: int
```

The command appends a new Annotation when `expected_revision` matches the current review stream. It never updates an existing annotation in place.

```python
class ReviewStateRead(BaseModel):
    snapshot_id: UUID
    tei_id: str
    revision: int
    workflow_state: ReviewWorkflowState
    current_annotation_id: UUID | None = None
```

`ReviewStateRead` is a workflow/concurrency projection. Annotation history remains the scholarly record.

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
