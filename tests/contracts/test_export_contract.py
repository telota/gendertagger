from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from gendertagger.models.classification import AgreementTier, CanonicalLabel, CertaintyTier
from gendertagger.models.export import (
    ExportCreateRequest,
    ExportExecution,
    ExportExecutionCreate,
    ExportFormat,
    ExportManifest,
    ExportManifestOutput,
    ExportPersonRecord,
    LabelSourcePolicy,
    TeiExportProfile,
)
from gendertagger.models.lifecycle import ExportExecutionStatus

pytestmark = pytest.mark.contract

CREATED_AT = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)


def _execution_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": uuid4(),
        "aggregation_execution_id": uuid4(),
        "format": ExportFormat.json,
        "label_source_policy": LabelSourcePolicy.machine_aggregation,
        "tei_profile": None,
        "human_resp_id": "#editor",
        "id": uuid4(),
        "status": ExportExecutionStatus.pending,
        "manifest_artifact_id": None,
        "started_at": None,
        "finished_at": None,
        "failure_class": None,
        "failure_diagnostic": None,
        "created_at": CREATED_AT,
    }
    payload.update(overrides)
    return payload


def test_export_format_enum_exposes_exact_public_values() -> None:
    assert {name: member.value for name, member in ExportFormat.__members__.items()} == {
        "tei": "tei",
        "json": "json",
        "csv": "csv",
    }


def test_label_source_policy_enum_exposes_exact_public_values() -> None:
    assert {name: member.value for name, member in LabelSourcePolicy.__members__.items()} == {
        "machine_aggregation": "machine_aggregation",
        "human_overrides": "human_overrides",
    }


def test_tei_export_profile_enum_exposes_exact_public_values() -> None:
    assert {name: member.value for name, member in TeiExportProfile.__members__.items()} == {
        "tei_p5_gender_v1": "tei_p5_gender_v1",
    }


def test_create_request_defaults_omit_a_tei_profile() -> None:
    request = ExportCreateRequest(
        run_id=uuid4(),
        aggregation_execution_id=uuid4(),
        format=ExportFormat.json,
    )

    assert request.tei_profile is None
    assert request.label_source_policy is LabelSourcePolicy.machine_aggregation


def test_create_request_rejects_a_tei_profile_for_a_non_tei_format() -> None:
    with pytest.raises(ValidationError):
        ExportCreateRequest(
            run_id=uuid4(),
            aggregation_execution_id=uuid4(),
            format=ExportFormat.json,
            tei_profile=TeiExportProfile.tei_p5_gender_v1,
        )


def test_create_request_accepts_a_tei_profile_for_tei_format() -> None:
    request = ExportCreateRequest(
        run_id=uuid4(),
        aggregation_execution_id=uuid4(),
        format=ExportFormat.tei,
        tei_profile=TeiExportProfile.tei_p5_gender_v1,
    )

    assert request.tei_profile is TeiExportProfile.tei_p5_gender_v1


def test_execution_create_requires_a_resolved_tei_profile_for_tei_format() -> None:
    with pytest.raises(ValidationError):
        ExportExecutionCreate(
            run_id=uuid4(),
            aggregation_execution_id=uuid4(),
            format=ExportFormat.tei,
        )


def test_execution_create_rejects_a_tei_profile_for_a_non_tei_format() -> None:
    with pytest.raises(ValidationError):
        ExportExecutionCreate(
            run_id=uuid4(),
            aggregation_execution_id=uuid4(),
            format=ExportFormat.csv,
            tei_profile=TeiExportProfile.tei_p5_gender_v1,
        )


def test_execution_create_accepts_a_resolved_tei_profile_for_tei_format() -> None:
    command = ExportExecutionCreate(
        run_id=uuid4(),
        aggregation_execution_id=uuid4(),
        format=ExportFormat.tei,
        tei_profile=TeiExportProfile.tei_p5_gender_v1,
    )

    assert command.tei_profile is TeiExportProfile.tei_p5_gender_v1


def test_export_execution_accepts_a_pending_resource() -> None:
    execution = ExportExecution.model_validate(_execution_payload())

    assert execution.status is ExportExecutionStatus.pending


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
            "manifest_artifact_id": None,
        },
        {
            "status": "pending",
            "manifest_artifact_id": str(uuid4()),
        },
        {
            "status": "failed",
            "started_at": CREATED_AT.isoformat(),
            "finished_at": CREATED_AT.isoformat(),
            "failure_diagnostic": None,
        },
        {
            "status": "pending",
            "failure_class": "InvalidResourceStateError",
        },
    ],
)
def test_export_execution_rejects_inconsistent_lifecycle_fields(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ExportExecution.model_validate(_execution_payload(**overrides))


def test_export_execution_accepts_a_completed_resource_with_a_manifest() -> None:
    execution = ExportExecution.model_validate(
        _execution_payload(
            status="completed",
            started_at=CREATED_AT.isoformat(),
            finished_at=CREATED_AT.isoformat(),
            manifest_artifact_id=str(uuid4()),
        )
    )

    assert execution.status is ExportExecutionStatus.completed


def _person_record(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "tei_id": "p1",
        "person_record_id": uuid4(),
        "label": CanonicalLabel.male,
        "evidence": "assigned",
        "resp": "#gendertagger",
        "cert": "high",
        "agreement_tier": AgreementTier.unanimous,
        "certainty_tier": CertaintyTier.high,
        "is_human_reviewed": False,
    }
    payload.update(overrides)
    return payload


def test_person_record_accepts_a_labeled_person() -> None:
    record = ExportPersonRecord.model_validate(_person_record())

    assert record.label is CanonicalLabel.male


def test_person_record_accepts_an_unlabeled_person_without_evidence() -> None:
    record = ExportPersonRecord.model_validate(
        _person_record(label=None, evidence=None, resp=None, cert=None)
    )

    assert record.label is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"label": None, "evidence": "assigned"},
        {"label": None, "resp": "#gendertagger"},
        {"label": None, "cert": "high"},
        {"evidence": None},
        {"resp": None},
        {"resp": ""},
        {"cert": "invalid"},
    ],
)
def test_person_record_rejects_inconsistent_label_evidence(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ExportPersonRecord.model_validate(_person_record(**overrides))


def test_manifest_requires_at_least_one_output() -> None:
    with pytest.raises(ValidationError):
        ExportManifest(
            export_execution_id=uuid4(),
            dataset_snapshot_id=uuid4(),
            source_snapshot_sha256="a" * 64,
            run_id=uuid4(),
            aggregation_execution_id=uuid4(),
            format=ExportFormat.json,
            label_source_policy=LabelSourcePolicy.machine_aggregation,
            tei_profile=None,
            outputs=(),
            generated_at=CREATED_AT,
        )


def test_manifest_accepts_one_output() -> None:
    manifest = ExportManifest(
        export_execution_id=uuid4(),
        dataset_snapshot_id=uuid4(),
        source_snapshot_sha256="a" * 64,
        run_id=uuid4(),
        aggregation_execution_id=uuid4(),
        format=ExportFormat.json,
        label_source_policy=LabelSourcePolicy.machine_aggregation,
        tei_profile=None,
        outputs=(
            ExportManifestOutput(
                logical_name="export.json",
                sha256="b" * 64,
                byte_size=10,
                media_type="application/json",
            ),
        ),
        generated_at=CREATED_AT,
    )

    assert len(manifest.outputs) == 1
