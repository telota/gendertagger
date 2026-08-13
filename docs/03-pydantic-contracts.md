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
```

## Person input contract

```python
class PersonInput(BaseModel):
    tei_id: str
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

## Prediction result contract

```python
class PredictionResult(BaseModel):
    label: CanonicalLabel | None
    status: PredictionStatus
    method_confidence: float | None = None
    raw_label: str | None = None
    raw_output: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Validation invariants:

- `status=success` requires a canonical `label`.
- `status in {abstain,error}` requires `label=None`.
- `method_confidence`, if present, must be in the method's declared range; `[0,1]` is preferred but not assumed globally unless adapter declares it.

## Method contract

Method implementations live in code and register a stable method identifier. Runtime configuration is YAML parsed through Pydantic.

Conceptual interface:

```python
class GenderMethod(Protocol):
    descriptor: MethodDescriptor

    def predict_batch(
        self,
        people: list[PersonInput],
        config: MethodConfig,
    ) -> list[PredictionResult]: ...
```

Batch-first design avoids a task per person while allowing adapters to use vectorized/GPU inference.

## Run configuration

A YAML file is input, but the **resolved Pydantic object** is authoritative for a run and is persisted with a canonical JSON representation and hash.

```python
class RunConfig(BaseModel):
    methods: list[MethodRunConfig]
    aggregation: AggregationConfig
    execution: ExecutionConfig
```

No service should read arbitrary YAML after a Run has been created. Workers consume the persisted resolved configuration.

## Celery task envelopes

Use small Pydantic envelopes, for example:

```python
class MethodBatchTask(BaseModel):
    method_execution_id: UUID
    batch_id: UUID
```

Workers load authoritative state from PostgreSQL. Do not serialize thousands of PersonInput objects into Redis.


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
class CurrentUser(BaseModel):
    id: UUID
    display_name: str
    roles: set[Role]
    project_permissions: dict[UUID, set[Permission]] = Field(default_factory=dict)
```

The exact identity provider is infrastructure. Services consume an explicit authenticated principal.

### Review concurrency

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
