"""Canonical anonymous classification requests, provenance, jobs, and task envelopes."""

from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from gendertagger.models.classification import PredictionResult
from gendertagger.models.common import UtcDatetime
from gendertagger.models.method import METHOD_NAME_PATTERN, MethodDescriptor
from gendertagger.models.project import SHA256_PATTERN
from gendertagger.models.run import QUEUE_NAME_PATTERN
from gendertagger.models.synchronous_classification import ClassifyNamesResponse

MAX_PUBLIC_CLASSIFICATION_BATCH_SIZE = 10_000
MAX_PUBLIC_CLASSIFICATION_NAME_LENGTH = 512
_SURROGATE_MINIMUM = 0xD800
_SURROGATE_MAXIMUM = 0xDFFF


def _validate_name_unicode(value: str) -> str:
    """Reject characters that PostgreSQL JSON and UTF-8 responses cannot represent."""
    if "\x00" in value or any(
        _SURROGATE_MINIMUM <= ord(character) <= _SURROGATE_MAXIMUM for character in value
    ):
        msg = "names must contain valid Unicode without U+0000"
        raise ValueError(msg)
    return value


PublicName = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PUBLIC_CLASSIFICATION_NAME_LENGTH),
    AfterValidator(_validate_name_unicode),
]
PublicMethodName = Annotated[str, Field(pattern=METHOD_NAME_PATTERN)]


class PublicClassifyNamesRequest(BaseModel):
    """Bounded names and optional server-allowlisted methods, without configuration overrides."""

    model_config = ConfigDict(extra="forbid")

    name: PublicName | None = Field(
        default=None, description="One name; mutually exclusive with names."
    )
    names: list[PublicName] | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_PUBLIC_CLASSIFICATION_BATCH_SIZE,
        description="Ordered batch of names; mutually exclusive with name.",
    )
    methods: list[PublicMethodName] | None = Field(
        default=None,
        min_length=1,
        max_length=20,
        description="Distinct public method identifiers; defaults to the deployment allowlist.",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_names(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        copied = dict(values)
        if isinstance(copied.get("name"), str):
            copied["name"] = copied["name"].strip()
        if isinstance(copied.get("names"), list):
            copied["names"] = [
                name.strip() if isinstance(name, str) else name for name in copied["names"]
            ]
        return copied

    @model_validator(mode="after")
    def _validate_name_choice(self) -> "PublicClassifyNamesRequest":
        if (self.name is None) == (self.names is None):
            msg = "supply exactly one of name or names"
            raise ValueError(msg)
        return self

    @field_validator("methods")
    @classmethod
    def _validate_distinct_methods(cls, values: list[str] | None) -> list[str] | None:
        if values is not None and len(values) != len(set(values)):
            msg = "methods must be distinct"
            raise ValueError(msg)
        return values

    def ordered_names(self) -> list[str]:
        """Return normalized inputs in their original order, preserving duplicates."""
        return [self.name] if self.name is not None else list(self.names or [])


class PublicClassificationProvenance(BaseModel):
    """Public, secret-free method versions and the exact execution environment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    methods: list[MethodDescriptor]
    method_configs: dict[str, dict[str, JsonValue]]
    method_revisions: dict[str, str] = Field(default_factory=dict)
    resolved_config_sha256: str = Field(pattern=SHA256_PATTERN)
    code_git_commit: str
    application_version: str
    python_version: str
    dependency_lock_sha256: str = Field(pattern=SHA256_PATTERN)
    dependency_versions: dict[str, str]
    container_image_digest: str | None = None
    aggregation_strategy: str = "reference_v1_or_selected_subset"


class PublicClassificationResponse(ClassifyNamesResponse):
    """Classification outputs plus the selected methods and execution provenance."""

    provenance: PublicClassificationProvenance
    predictions: list[dict[str, PredictionResult]] = Field(
        description="Method raw outputs and normalization provenance, with secrets and diagnostics removed."
    )


class PublicClassificationMethod(BaseModel):
    """One selectable method and whether it always uses a persisted job."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    descriptor: MethodDescriptor
    asynchronous: bool


class PublicClassificationMethods(BaseModel):
    """Deployment-owned anonymous classification capabilities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    methods: list[PublicClassificationMethod]
    synchronous_batch_size: int
    maximum_batch_size: int = MAX_PUBLIC_CLASSIFICATION_BATCH_SIZE


class PublicClassificationStatus(StrEnum):
    """Durable public classification job lifecycle."""

    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class PublicClassificationJob(BaseModel):
    """Secret-free domain resource returned on acceptance and capability-authorized polling."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    status: PublicClassificationStatus
    name_count: int = Field(ge=1)
    provenance: PublicClassificationProvenance
    response: PublicClassificationResponse | None = None
    failure_code: str | None = None
    created_at: UtcDatetime
    started_at: UtcDatetime | None = None
    completed_at: UtcDatetime | None = None


class PublicClassificationJobAccepted(PublicClassificationJob):
    """Accepted job and its one-time polling capability, never included in ordinary reads."""

    retrieval_token: str


class PublicClassificationJobRecord(BaseModel):
    """Internal persisted immutable inputs and lease-fenced classification outputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    queue_name: str = Field(default="cpu", pattern=QUEUE_NAME_PATTERN, max_length=100)
    retrieval_token_sha256: str = Field(pattern=SHA256_PATTERN)
    names: list[str]
    methods: list[str]
    resolved_method_configs: dict[str, dict[str, JsonValue]]
    provenance: PublicClassificationProvenance
    status: PublicClassificationStatus = PublicClassificationStatus.queued
    response: ClassifyNamesResponse | None = None
    raw_predictions: list[dict[str, PredictionResult]] | None = None
    failure_code: str | None = None
    created_at: UtcDatetime
    started_at: UtcDatetime | None = None
    completed_at: UtcDatetime | None = None
    lease_id: UUID | None = None
    lease_until: UtcDatetime | None = None


class PublicClassificationTaskMessage(BaseModel):
    """Identifier-only broker envelope; names and configuration stay in persistence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    classification_job_id: UUID
