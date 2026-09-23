from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from gendertagger.domain.aggregation import REFERENCE_POOLED_METHODS
from gendertagger.models.classification import AgreementTier, CanonicalLabel, CertaintyTier
from gendertagger.models.evaluation import (
    BenchmarkSummary,
    EnsembleMetrics,
    EvaluationCreateRequest,
    EvaluationDefinition,
    EvaluationDefinitionId,
    EvaluationExecution,
    EvaluationExecutionCreate,
    KappaCell,
    MethodAccuracy,
    MethodCoverage,
    RecallWithCI,
)
from gendertagger.models.lifecycle import EvaluationExecutionStatus

pytestmark = pytest.mark.contract

CREATED_AT = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)


def _execution_payload(**overrides: object) -> dict[str, object]:
    command = EvaluationExecutionCreate(
        run_id=uuid4(),
        method_execution_ids=(uuid4(), uuid4()),
    )
    payload: dict[str, object] = {
        **command.model_dump(mode="json"),
        "id": uuid4(),
        "config_sha256": command.canonical_config_sha256(),
        "status": EvaluationExecutionStatus.pending,
        "report_artifact_id": None,
        "started_at": None,
        "finished_at": None,
        "failure_class": None,
        "failure_diagnostic": None,
        "created_at": CREATED_AT,
    }
    payload.update(overrides)
    return payload


def test_evaluation_definition_id_enum_exposes_exact_public_values() -> None:
    assert {name: member.value for name, member in EvaluationDefinitionId.__members__.items()} == {
        "gnd_benchmark_v1": "gnd_benchmark_v1",
    }


def test_default_scored_methods_matches_the_reference_pooled_roster() -> None:
    # models must stay independent of domain (import-linter), so the default
    # is a models-local literal; this guards it from drifting out of sync
    # with gendertagger.domain.aggregation.REFERENCE_POOLED_METHODS.
    assert EvaluationDefinition().scored_methods == REFERENCE_POOLED_METHODS


def test_default_definition_reproduces_the_published_nine_method_roster() -> None:
    definition = EvaluationDefinition()

    assert definition.required_methods == (
        "gnd",
        "gender_guesser",
        "wiki_gendersort",
        "hivoto",
        "nomquamgender",
        "hf_distilbert",
        "hf_genderize",
        "local_llm",
        "hivoto_xgboost",
    )
    assert definition.kappa_methods == (
        "gender_guesser",
        "wiki_gendersort",
        "hivoto",
        "nomquamgender",
        "hf_distilbert",
        "hf_genderize",
        "local_llm",
        "hivoto_xgboost",
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"benchmark_method": "gnd", "scored_methods": ("gnd", "hivoto")},
        {"benchmark_method": "gnd", "kappa_extra_methods": ("gnd",)},
        {"scored_methods": ("hivoto", "hivoto")},
        {"kappa_extra_methods": ("hivoto_xgboost", "hivoto_xgboost")},
        {"scored_methods": ("hivoto",), "kappa_extra_methods": ("hivoto",)},
        {"scored_methods": ("Not-Valid",)},
        {"benchmark_method": "Not Valid"},
        {"benchmark_label_filter": ()},
        {"benchmark_label_filter": (CanonicalLabel.male, CanonicalLabel.male)},
        {"scored_methods": ()},
    ],
)
def test_evaluation_definition_rejects_invalid_rosters(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        EvaluationDefinition.model_validate(overrides)


def test_evaluation_create_request_accepts_unique_method_execution_ids() -> None:
    request = EvaluationCreateRequest(
        run_id=uuid4(),
        method_execution_ids=(uuid4(), uuid4()),
    )

    assert len(request.method_execution_ids) == 2


def test_evaluation_create_request_rejects_duplicate_method_execution_ids() -> None:
    duplicate_id = uuid4()

    with pytest.raises(ValidationError):
        EvaluationCreateRequest(
            run_id=uuid4(),
            method_execution_ids=(duplicate_id, duplicate_id),
        )


def test_benchmark_summary_requires_class_counts_to_sum_to_size() -> None:
    with pytest.raises(ValidationError):
        BenchmarkSummary(
            method_name="gnd",
            labels=(CanonicalLabel.male, CanonicalLabel.female),
            size=2,
            class_counts={CanonicalLabel.male: 1, CanonicalLabel.female: 2},
        )


def test_benchmark_summary_requires_class_counts_keys_to_match_labels() -> None:
    with pytest.raises(ValidationError):
        BenchmarkSummary(
            method_name="gnd",
            labels=(CanonicalLabel.male, CanonicalLabel.female),
            size=1,
            class_counts={CanonicalLabel.male: 1},
        )


def test_method_coverage_requires_label_distribution_to_sum_to_coverage_count() -> None:
    with pytest.raises(ValidationError):
        MethodCoverage(
            method_name="gnd",
            total=5,
            coverage_count=3,
            coverage_share=0.6,
            label_distribution={
                CanonicalLabel.male: 1,
                CanonicalLabel.female: 1,
                CanonicalLabel.unknown: 0,
                CanonicalLabel.institution: 0,
            },
            abstain_count=0,
            error_count=0,
        )


def test_method_coverage_requires_counts_to_sum_to_total() -> None:
    with pytest.raises(ValidationError):
        MethodCoverage(
            method_name="gnd",
            total=5,
            coverage_count=2,
            coverage_share=0.4,
            label_distribution={
                CanonicalLabel.male: 1,
                CanonicalLabel.female: 1,
                CanonicalLabel.unknown: 0,
                CanonicalLabel.institution: 0,
            },
            abstain_count=0,
            error_count=0,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"correct": 6, "class_size": 5},
        {"ci_low": 0.9, "ci_high": 0.1},
    ],
)
def test_recall_with_ci_rejects_inconsistent_bounds(payload: dict[str, object]) -> None:
    base = {
        "label": CanonicalLabel.male,
        "class_size": 5,
        "correct": 3,
        "recall": 0.6,
        "ci_low": 0.2,
        "ci_high": 0.9,
    }
    with pytest.raises(ValidationError):
        RecallWithCI.model_validate({**base, **payload})


def test_method_accuracy_rejects_correct_exceeding_answered() -> None:
    with pytest.raises(ValidationError):
        MethodAccuracy(
            method_name="gender_guesser",
            answered_count=1,
            correct_count=2,
            accuracy=1.0,
            effective_accuracy=1.0,
            confusion_matrix={CanonicalLabel.male: {CanonicalLabel.male: 2}},
            recall=(),
        )


def test_kappa_cell_rejects_identical_methods() -> None:
    with pytest.raises(ValidationError):
        KappaCell(method_a="hivoto", method_b="hivoto", co_answered_count=10, kappa=0.5)


def test_kappa_cell_rejects_kappa_without_positive_co_answered_count() -> None:
    with pytest.raises(ValidationError):
        KappaCell(method_a="a", method_b="b", co_answered_count=0, kappa=0.5)


def test_kappa_cell_allows_no_kappa_with_zero_co_answered_count() -> None:
    cell = KappaCell(method_a="a", method_b="b", co_answered_count=0, kappa=None)

    assert cell.kappa is None


def test_ensemble_metrics_rejects_correction_exceeding_reviewed_count() -> None:
    with pytest.raises(ValidationError):
        EnsembleMetrics(
            canonical_label_distribution=dict.fromkeys(CanonicalLabel, 0),
            agreement_tier_distribution=dict.fromkeys(AgreementTier, 0),
            certainty_tier_distribution=dict.fromkeys(CertaintyTier, 0),
            human_reviewed_count=1,
            human_correction_count=2,
        )


def test_evaluation_execution_accepts_a_pending_resource() -> None:
    execution = EvaluationExecution.model_validate(_execution_payload())

    assert execution.status is EvaluationExecutionStatus.pending


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "completed", "finished_at": None},
        {"status": "running", "finished_at": None},
        {"status": "pending", "finished_at": CREATED_AT.isoformat()},
        {
            "status": "completed",
            "started_at": CREATED_AT.isoformat(),
            "finished_at": CREATED_AT.isoformat(),
            "report_artifact_id": None,
        },
        {
            "status": "pending",
            "report_artifact_id": str(uuid4()),
        },
        {
            "status": "failed",
            "started_at": CREATED_AT.isoformat(),
            "finished_at": CREATED_AT.isoformat(),
            "failure_diagnostic": None,
        },
        {
            "status": "pending",
            "failure_class": "EvaluationInputError",
        },
    ],
)
def test_evaluation_execution_rejects_inconsistent_lifecycle_fields(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        EvaluationExecution.model_validate(_execution_payload(**overrides))


def test_evaluation_execution_accepts_a_completed_resource_with_a_report() -> None:
    execution = EvaluationExecution.model_validate(
        _execution_payload(
            status="completed",
            started_at=CREATED_AT.isoformat(),
            finished_at=CREATED_AT.isoformat(),
            report_artifact_id=str(uuid4()),
        )
    )

    assert execution.status is EvaluationExecutionStatus.completed
    assert execution.report_artifact_id is not None
