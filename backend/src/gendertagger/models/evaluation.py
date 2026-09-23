"""Canonical contracts for versioned benchmark evaluation definitions and reports."""

import re
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from gendertagger.models.aggregation import AggregatedResult, AggregationPersonPredictions
from gendertagger.models.classification import AgreementTier, CanonicalLabel, CertaintyTier
from gendertagger.models.common import UtcDatetime, canonical_json_sha256
from gendertagger.models.lifecycle import EvaluationExecutionStatus
from gendertagger.models.method import METHOD_NAME_PATTERN
from gendertagger.models.project import SHA256_PATTERN

_METHOD_NAME_RE = re.compile(METHOD_NAME_PATTERN)

# Mirrors gendertagger.domain.aggregation.REFERENCE_POOLED_METHODS. Canonical
# models must stay independent of domain logic (see the import-linter
# contract), so this default is a literal rather than an import; a contract
# test guards the two from drifting apart.
_DEFAULT_SCORED_METHODS = (
    "gender_guesser",
    "wiki_gendersort",
    "hivoto",
    "nomquamgender",
    "hf_distilbert",
    "hf_genderize",
    "local_llm",
)


def _validate_method_names(names: tuple[str, ...]) -> tuple[str, ...]:
    invalid = [name for name in names if not _METHOD_NAME_RE.fullmatch(name)]
    if invalid:
        msg = f"invalid method names: {', '.join(invalid)}"
        raise ValueError(msg)
    return names


class EvaluationDefinitionId(StrEnum):
    """Supported versioned evaluation definitions."""

    gnd_benchmark_v1 = "gnd_benchmark_v1"


class EvaluationDefinition(BaseModel):
    """Versioned benchmark and metric configuration for one evaluation.

    An evaluation is general-purpose: any method-execution subset may be
    scored against any configured benchmark label source. ``gnd_benchmark_v1``
    is the default, reproducing the published reference study's exact rules
    (a gendered-only GND benchmark, a 7-method accuracy/recall table, and an
    8-method Cohen's kappa matrix), but future definitions may configure a
    different benchmark method, label filter, or method roster without
    changing the evaluation engine itself.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: EvaluationDefinitionId = EvaluationDefinitionId.gnd_benchmark_v1
    benchmark_method: str = Field(default="gnd", pattern=METHOD_NAME_PATTERN)
    benchmark_label_filter: tuple[CanonicalLabel, ...] = (
        CanonicalLabel.male,
        CanonicalLabel.female,
    )
    scored_methods: tuple[str, ...] = Field(default=_DEFAULT_SCORED_METHODS, min_length=1)
    kappa_extra_methods: tuple[str, ...] = ("hivoto_xgboost",)
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def _validate_method_roster(self) -> Self:
        _validate_method_names(self.scored_methods)
        _validate_method_names(self.kappa_extra_methods)

        if len(set(self.benchmark_label_filter)) != len(self.benchmark_label_filter):
            msg = "benchmark_label_filter must not contain duplicates"
            raise ValueError(msg)
        if not self.benchmark_label_filter:
            msg = "benchmark_label_filter must not be empty"
            raise ValueError(msg)

        if len(set(self.scored_methods)) != len(self.scored_methods):
            msg = "scored_methods must not contain duplicates"
            raise ValueError(msg)
        if len(set(self.kappa_extra_methods)) != len(self.kappa_extra_methods):
            msg = "kappa_extra_methods must not contain duplicates"
            raise ValueError(msg)

        scored = set(self.scored_methods)
        kappa_extra = set(self.kappa_extra_methods)
        if self.benchmark_method in scored:
            msg = "benchmark_method must not also be a scored method"
            raise ValueError(msg)
        if self.benchmark_method in kappa_extra:
            msg = "benchmark_method must not also be a kappa_extra_method"
            raise ValueError(msg)
        if scored & kappa_extra:
            overlap = ", ".join(sorted(scored & kappa_extra))
            msg = f"kappa_extra_methods must be disjoint from scored_methods: {overlap}"
            raise ValueError(msg)
        return self

    @property
    def required_methods(self) -> tuple[str, ...]:
        """Every method whose Prediction the evaluation executor must load.

        The union of the benchmark method, scored methods, and kappa-only
        methods, deduplicated and in deterministic order.
        """
        return (self.benchmark_method, *self.scored_methods, *self.kappa_extra_methods)

    @property
    def kappa_methods(self) -> tuple[str, ...]:
        """Methods entering the pairwise Cohen's kappa matrix."""
        return (*self.scored_methods, *self.kappa_extra_methods)


class EvaluationCreateRequest(BaseModel):
    """Public command selecting one run, definition, and exact method executions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    definition: EvaluationDefinitionId = EvaluationDefinitionId.gnd_benchmark_v1
    method_execution_ids: tuple[UUID, ...] = Field(min_length=1)
    aggregation_execution_id: UUID | None = None

    @model_validator(mode="after")
    def _validate_unique_method_executions(self) -> Self:
        if len(set(self.method_execution_ids)) != len(self.method_execution_ids):
            msg = "method_execution_ids must not contain duplicates"
            raise ValueError(msg)
        return self


class BenchmarkSummary(BaseModel):
    """Size and per-label composition of the resolved benchmark subset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    method_name: str = Field(pattern=METHOD_NAME_PATTERN)
    labels: tuple[CanonicalLabel, ...]
    size: int = Field(ge=0)
    class_counts: dict[CanonicalLabel, int]

    @model_validator(mode="after")
    def _validate_class_counts(self) -> Self:
        if set(self.class_counts) != set(self.labels):
            msg = "class_counts must have exactly one entry per benchmark label"
            raise ValueError(msg)
        if sum(self.class_counts.values()) != self.size:
            msg = "class_counts must sum to the benchmark size"
            raise ValueError(msg)
        return self


class MethodCoverage(BaseModel):
    """Corpus-wide coverage and label distribution for one evaluated method."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    method_name: str = Field(pattern=METHOD_NAME_PATTERN)
    total: int = Field(ge=0)
    coverage_count: int = Field(ge=0)
    coverage_share: float = Field(ge=0.0, le=1.0)
    label_distribution: dict[CanonicalLabel, int]
    abstain_count: int = Field(ge=0)
    error_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_counts(self) -> Self:
        if sum(self.label_distribution.values()) != self.coverage_count:
            msg = "label_distribution must sum to coverage_count"
            raise ValueError(msg)
        if self.coverage_count + self.abstain_count + self.error_count != self.total:
            msg = "coverage_count, abstain_count, and error_count must sum to total"
            raise ValueError(msg)
        return self


class RecallWithCI(BaseModel):
    """Per-class recall against the benchmark, with a two-sided confidence interval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: CanonicalLabel
    class_size: int = Field(ge=0)
    correct: int = Field(ge=0)
    recall: float = Field(ge=0.0, le=1.0)
    ci_low: float = Field(ge=0.0, le=1.0)
    ci_high: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_recall_bounds(self) -> Self:
        if self.correct > self.class_size:
            msg = "correct must not exceed class_size"
            raise ValueError(msg)
        if self.ci_low > self.ci_high:
            msg = "ci_low must not exceed ci_high"
            raise ValueError(msg)
        return self


class MethodAccuracy(BaseModel):
    """Benchmark-scoped accuracy, recall, and confusion matrix for one scored method."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    method_name: str = Field(pattern=METHOD_NAME_PATTERN)
    answered_count: int = Field(ge=0)
    correct_count: int = Field(ge=0)
    accuracy: float = Field(ge=0.0, le=1.0)
    effective_accuracy: float = Field(ge=0.0, le=1.0)
    confusion_matrix: dict[CanonicalLabel, dict[CanonicalLabel, int]]
    recall: tuple[RecallWithCI, ...]

    @model_validator(mode="after")
    def _validate_correct_within_answered(self) -> Self:
        if self.correct_count > self.answered_count:
            msg = "correct_count must not exceed answered_count"
            raise ValueError(msg)
        return self


class KappaCell(BaseModel):
    """Pairwise Cohen's kappa restricted to entries both methods answered."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    method_a: str = Field(pattern=METHOD_NAME_PATTERN)
    method_b: str = Field(pattern=METHOD_NAME_PATTERN)
    co_answered_count: int = Field(ge=0)
    kappa: float | None = Field(default=None, ge=-1.0, le=1.0)

    @model_validator(mode="after")
    def _validate_distinct_methods(self) -> Self:
        if self.method_a == self.method_b:
            msg = "method_a and method_b must be distinct"
            raise ValueError(msg)
        if self.co_answered_count == 0 and self.kappa is not None:
            msg = "kappa requires a positive co_answered_count"
            raise ValueError(msg)
        return self


class EnsembleMetrics(BaseModel):
    """Record-level aggregation and review metrics over an evaluated run snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_label_distribution: dict[CanonicalLabel, int]
    agreement_tier_distribution: dict[AgreementTier, int]
    certainty_tier_distribution: dict[CertaintyTier, int]
    human_reviewed_count: int = Field(ge=0)
    human_correction_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_review_counts(self) -> Self:
        if self.human_correction_count > self.human_reviewed_count:
            msg = "human_correction_count must not exceed human_reviewed_count"
            raise ValueError(msg)
        return self


class EvaluationReport(BaseModel):
    """Immutable computed evaluation output, persisted as a checksummed JSON artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    definition: EvaluationDefinitionId
    benchmark: BenchmarkSummary
    coverage: tuple[MethodCoverage, ...]
    accuracy: tuple[MethodAccuracy, ...]
    kappa_matrix: tuple[KappaCell, ...]
    ensemble: EnsembleMetrics | None = None


class EvaluationTaskMessage(BaseModel):
    """Small validated envelope requesting one persisted evaluation execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evaluation_execution_id: UUID


class EvaluationExecutionCreate(BaseModel):
    """Validated definition and exact method selection for one evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    definition: EvaluationDefinitionId = EvaluationDefinitionId.gnd_benchmark_v1
    resolved_config: dict[str, JsonValue] = Field(default_factory=dict)
    method_execution_ids: tuple[UUID, ...] = Field(min_length=1)
    aggregation_execution_id: UUID | None = None

    @model_validator(mode="after")
    def _validate_unique_method_executions(self) -> Self:
        if len(set(self.method_execution_ids)) != len(self.method_execution_ids):
            msg = "method_execution_ids must not contain duplicates"
            raise ValueError(msg)
        return self

    def canonical_config_sha256(self) -> str:
        """Hash the versioned definition and its resolved configuration."""
        return canonical_json_sha256(
            {
                "definition": self.definition.value,
                "config": self.resolved_config,
            }
        )


class EvaluationExecution(EvaluationExecutionCreate):
    """Canonical read model for one independently rerunnable evaluation."""

    id: UUID
    config_sha256: str = Field(pattern=SHA256_PATTERN)
    status: EvaluationExecutionStatus
    report_artifact_id: UUID | None = None
    started_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None
    failure_class: str | None = None
    failure_diagnostic: str | None = None
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _validate_lifecycle_fields(self) -> Self:
        terminal_statuses = {
            EvaluationExecutionStatus.completed,
            EvaluationExecutionStatus.failed,
            EvaluationExecutionStatus.cancelled,
        }
        if self.status in terminal_statuses:
            if self.finished_at is None:
                msg = "a terminal evaluation requires finished_at"
                raise ValueError(msg)
        elif self.finished_at is not None:
            msg = "a non-terminal evaluation must not have finished_at"
            raise ValueError(msg)
        if (
            self.status in {EvaluationExecutionStatus.running, EvaluationExecutionStatus.completed}
            and self.started_at is None
        ):
            msg = "a running or completed evaluation requires started_at"
            raise ValueError(msg)
        if self.status is EvaluationExecutionStatus.completed:
            if self.report_artifact_id is None:
                msg = "a completed evaluation requires a report artifact"
                raise ValueError(msg)
        elif self.report_artifact_id is not None:
            msg = "only a completed evaluation may have a report artifact"
            raise ValueError(msg)
        if self.status is EvaluationExecutionStatus.failed:
            if self.failure_diagnostic is None or not self.failure_diagnostic.strip():
                msg = "a failed evaluation requires a failure diagnostic"
                raise ValueError(msg)
        elif self.failure_class is not None or self.failure_diagnostic is not None:
            msg = "only a failed evaluation may have failure details"
            raise ValueError(msg)
        return self


class EvaluationInputs(BaseModel):
    """Loaded evidence for one running evaluation, ready for pure computation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    corpus: tuple[AggregationPersonPredictions, ...]
    aggregated_results: tuple[AggregatedResult, ...] | None = None
    human_reviewed_count: int = Field(default=0, ge=0)
    human_correction_count: int = Field(default=0, ge=0)
