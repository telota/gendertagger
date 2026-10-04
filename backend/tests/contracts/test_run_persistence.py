from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError
from tests.seeding import seed_worker_provenance

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.models.classification import CanonicalLabel, PredictionResult, PredictionStatus
from gendertagger.models.lifecycle import MethodExecutionStatus, RunStatus, TaskBatchStatus
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.run import (
    MethodExecution,
    MethodExecutionCreate,
    MethodExecutionPredictionSummary,
    MethodExecutionResult,
    MethodExecutionResultFilter,
    MethodExecutionResultState,
    Prediction,
    PredictionWrite,
    Progress,
    Run,
    RunCreateRequest,
    TaskBatch,
    WorkerProvenance,
)

RUN_ID = UUID("50000000-0000-0000-0000-000000000001")
SNAPSHOT_ID = UUID("20000000-0000-0000-0000-000000000001")
EXECUTION_ID = UUID("60000000-0000-0000-0000-000000000001")
BATCH_ID = UUID("65000000-0000-0000-0000-000000000001")
PERSON_ID = UUID("40000000-0000-0000-0000-000000000001")
PREDICTION_ID = UUID("70000000-0000-0000-0000-000000000001")
CREATED_AT = datetime(2026, 8, 13, 10, 0, tzinfo=UTC)
SHA256 = "b" * 64
RUN_CONFIG = RunConfig(methods=[MethodRunConfig(name="demo_method")])


def run_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": RUN_ID,
        "dataset_snapshot_id": SNAPSHOT_ID,
        "resolved_config": RUN_CONFIG,
        "config_sha256": RUN_CONFIG.canonical_sha256(),
        "status": RunStatus.created,
        "code_git_commit": "abc123",
        "application_version": "0.0.0",
        "container_image_digest": None,
        "python_version": "3.13.14",
        "dependency_lock_sha256": None,
        "dependency_lock_artifact_id": None,
        "started_at": None,
        "finished_at": None,
        "failure_diagnostic": None,
        "created_at": CREATED_AT,
        "progress": Progress(),
    }
    payload.update(overrides)
    return payload


def execution_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": EXECUTION_ID,
        "run_id": RUN_ID,
        "method_name": "demo_method",
        "implementation_version": "1.0.0",
        "normalization_version": "demo_v1",
        "resolved_config": {},
        "config_sha256": "c" * 64,
        "status": MethodExecutionStatus.pending,
        "queue_name": "cpu",
        "model_identifier": None,
        "model_revision": None,
        "model_checksum": None,
        "model_artifact_id": None,
        "data_artifact_id": None,
        "prompt_version": None,
        "schema_version": None,
        "worker_metadata": {},
        "total_count": 2,
        "completed_count": 0,
        "failed_count": 0,
        "started_at": None,
        "finished_at": None,
        "failure_class": None,
        "failure_diagnostic": None,
        "created_at": CREATED_AT,
        "progress": Progress(),
    }
    payload.update(overrides)
    return payload


def test_run_create_request_excludes_server_owned_provenance() -> None:
    command = RunCreateRequest(
        dataset_snapshot_id=SNAPSHOT_ID,
        config=RUN_CONFIG,
    )

    assert command.model_dump(mode="json") == {
        "dataset_snapshot_id": str(SNAPSHOT_ID),
        "config": RUN_CONFIG.model_dump(mode="json"),
    }
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RunCreateRequest.model_validate(
            {
                "dataset_snapshot_id": SNAPSHOT_ID,
                "config": RUN_CONFIG,
                "code_git_commit": "untrusted",
            }
        )


def test_run_accepts_created_and_completed_lifecycle_shapes() -> None:
    created = Run.model_validate(run_payload())
    completed = Run.model_validate(
        run_payload(
            status=RunStatus.completed,
            started_at=CREATED_AT,
            finished_at=CREATED_AT,
        )
    )

    assert created.status is RunStatus.created
    assert completed.finished_at == CREATED_AT


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"status": RunStatus.completed}, "terminal run requires finished_at"),
        ({"finished_at": CREATED_AT}, "non-terminal run must not have finished_at"),
        ({"status": RunStatus.running}, "running or completed run requires started_at"),
        ({"started_at": CREATED_AT}, "has not started must not have started_at"),
        ({"status": RunStatus.failed, "finished_at": CREATED_AT}, "requires a failure diagnostic"),
        ({"failure_diagnostic": "failure"}, "only a failed run may have a failure diagnostic"),
        ({"failure_class": "RuntimeError"}, "only a failed run may have a failure class"),
    ],
)
def test_run_rejects_inconsistent_lifecycle_fields(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        Run.model_validate(run_payload(**overrides))


def test_method_execution_config_hash_is_order_independent() -> None:
    descriptor = MethodDescriptor(
        name="demo_method",
        implementation_version="1.0.0",
        normalization_version="demo_v1",
    )
    first = MethodExecutionCreate(
        run_id=RUN_ID,
        descriptor=descriptor,
        resolved_config={"threshold": 0.5, "nested": {"enabled": True}},
        queue_name="cpu",
    )
    second = MethodExecutionCreate(
        run_id=RUN_ID,
        descriptor=descriptor,
        resolved_config={"nested": {"enabled": True}, "threshold": 0.5},
        queue_name="cpu",
    )

    assert first.config_sha256() == second.config_sha256()


def test_method_execution_rejects_progress_beyond_total() -> None:
    with pytest.raises(ValidationError, match="progress must not exceed total_count"):
        MethodExecution.model_validate(execution_payload(completed_count=2, failed_count=1))


def test_prediction_write_and_read_preserve_unknown_as_success() -> None:
    result = PredictionResult(
        label=CanonicalLabel.unknown,
        status=PredictionStatus.success,
        method_confidence=None,
        raw_label="unknown",
        raw_output={"label": "unknown"},
        metadata={"normalization_version": "demo_v1"},
    )
    write = PredictionWrite(
        person_record_id=PERSON_ID,
        task_batch_id=BATCH_ID,
        input_fingerprint=SHA256,
        result=result,
    )
    prediction = Prediction(
        id=PREDICTION_ID,
        method_execution_id=EXECUTION_ID,
        person_record_id=PERSON_ID,
        task_batch_id=BATCH_ID,
        input_fingerprint=SHA256,
        created_at=CREATED_AT,
        **result.model_dump(),
    )

    assert write.result.status is PredictionStatus.success
    assert prediction.label is CanonicalLabel.unknown
    assert prediction.status is PredictionStatus.success


def test_method_execution_result_projection_distinguishes_missing_from_unknown() -> None:
    persisted = MethodExecutionResult(
        method_execution_id=EXECUTION_ID,
        dataset_snapshot_id=SNAPSHOT_ID,
        person_record_id=PERSON_ID,
        tei_id="p1",
        result_state=MethodExecutionResultState.success,
        prediction_id=PREDICTION_ID,
        prediction=MethodExecutionPredictionSummary(
            label=CanonicalLabel.unknown,
            status=PredictionStatus.success,
            raw_label="uncertain",
        ),
    )
    missing = MethodExecutionResult(
        method_execution_id=EXECUTION_ID,
        dataset_snapshot_id=SNAPSHOT_ID,
        person_record_id=PERSON_ID,
        tei_id="p1",
        result_state=MethodExecutionResultState.missing,
    )

    assert persisted.prediction is not None
    assert persisted.prediction.label is CanonicalLabel.unknown
    assert missing.prediction is None
    with pytest.raises(
        ValidationError, match="missing prediction requires the missing result state"
    ):
        MethodExecutionResult(
            method_execution_id=EXECUTION_ID,
            dataset_snapshot_id=SNAPSHOT_ID,
            person_record_id=PERSON_ID,
            tei_id="p1",
            result_state=MethodExecutionResultState.success,
        )
    with pytest.raises(ValidationError, match="label filter requires successful"):
        MethodExecutionResultFilter(
            label=CanonicalLabel.unknown,
            result_state=MethodExecutionResultState.abstain,
        )


@pytest.mark.parametrize(
    "override",
    [
        {"code_git_commit": " "},
        {"code_git_commit": "c" * 101},
        {"application_version": "a" * 101},
        {"python_version": "p" * 101},
        {"application_version": ""},
        {"python_version": " "},
        {"dependency_lock_sha256": "not-a-digest"},
        {"dependency_versions": {}},
        {"dependency_versions": {"": "1"}},
        {"dependency_versions": {"pydantic": " "}},
        {"hostname": " "},
        {"process_id": 0},
        {"undeclared_identity": "forbidden"},
        {"hostname": "h" * 256},
    ],
)
def test_worker_provenance_rejects_incomplete_or_open_identity(
    override: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        WorkerProvenance.model_validate({**seed_worker_provenance().model_dump(), **override})


def test_worker_receipt_is_frozen_and_historical_reads_preserve_unknown_evidence() -> None:
    worker = seed_worker_provenance()
    with pytest.raises(ValidationError, match="frozen"):
        worker.hostname = "rewritten"
    historical_run = Run.model_validate(run_payload())
    historical_batch = TaskBatch(
        id=BATCH_ID,
        method_execution_id=EXECUTION_ID,
        batch_index=0,
        queue_name="cpu",
        record_offset=0,
        record_count=1,
        status=TaskBatchStatus.pending,
        attempt_count=0,
        success_count=0,
        abstain_count=0,
        error_count=0,
        created_at=CREATED_AT,
    )
    assert historical_run.dependency_versions is None
    assert historical_batch.worker_provenance is None
