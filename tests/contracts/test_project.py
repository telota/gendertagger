from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from gendertagger.models.lifecycle import DatasetSnapshotStatus
from gendertagger.models.person import PersonRecord
from gendertagger.models.project import (
    DatasetSnapshot,
    DatasetSnapshotCreate,
    ProjectCreate,
    SnapshotImportRequest,
    TeiImportProfile,
)

PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
SNAPSHOT_ID = UUID("20000000-0000-0000-0000-000000000001")
ARTIFACT_ID = UUID("30000000-0000-0000-0000-000000000001")
PERSON_ID = UUID("40000000-0000-0000-0000-000000000001")
SHA256 = "a" * 64
CREATED_AT = datetime(2026, 8, 13, 10, 0, tzinfo=UTC)


def snapshot_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": SNAPSHOT_ID,
        "project_id": PROJECT_ID,
        "source_artifact_id": ARTIFACT_ID,
        "source_sha256": SHA256,
        "parser_version": "tei_parser_v1",
        "import_config": {"profile": TeiImportProfile.tei_p5_person_register_v1.value},
        "status": DatasetSnapshotStatus.pending,
        "record_count": None,
        "ready_at": None,
        "failure_diagnostic": None,
        "created_at": CREATED_AT,
    }
    payload.update(overrides)
    return payload


def test_project_create_rejects_blank_display_name_and_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="display_name must not be blank"):
        ProjectCreate(slug="edition", display_name="  ")
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ProjectCreate.model_validate(
            {"slug": "edition", "display_name": "Edition", "unexpected": True}
        )


def test_snapshot_import_request_uses_one_versioned_closed_profile() -> None:
    command = SnapshotImportRequest()

    assert command.model_dump(mode="json") == {
        "profile": TeiImportProfile.tei_p5_person_register_v1.value
    }
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SnapshotImportRequest.model_validate({"unknown_option": True})


@pytest.mark.parametrize("slug", ["Uppercase", "two_words", "-leading", "trailing-"])
def test_project_create_rejects_noncanonical_slug(slug: str) -> None:
    with pytest.raises(ValidationError):
        ProjectCreate(slug=slug, display_name="Edition")


def test_snapshot_create_requires_json_compatible_config_and_sha256() -> None:
    with pytest.raises(ValidationError):
        DatasetSnapshotCreate(
            project_id=PROJECT_ID,
            source_artifact_id=ARTIFACT_ID,
            source_sha256="not-a-sha256",
            parser_version="tei_parser_v1",
        )
    with pytest.raises(ValidationError):
        DatasetSnapshotCreate.model_validate(
            {
                "project_id": PROJECT_ID,
                "source_artifact_id": ARTIFACT_ID,
                "source_sha256": SHA256,
                "parser_version": "tei_parser_v1",
                "import_config": {"unsupported": object()},
            }
        )


def test_snapshot_normalizes_aware_timestamps_to_utc() -> None:
    offset = timezone(timedelta(hours=2))
    snapshot = DatasetSnapshot.model_validate(
        snapshot_payload(created_at=datetime(2026, 8, 13, 12, 0, tzinfo=offset))
    )

    assert snapshot.created_at == CREATED_AT
    assert snapshot.created_at.tzinfo is UTC


def test_snapshot_rejects_naive_timestamps() -> None:
    naive_timestamp = datetime(2026, 8, 13, 10, 0)  # noqa: DTZ001  # Rejection fixture.
    with pytest.raises(ValidationError, match="timestamp must be timezone-aware"):
        DatasetSnapshot.model_validate(snapshot_payload(created_at=naive_timestamp))


def test_ready_snapshot_requires_complete_success_metadata() -> None:
    with pytest.raises(ValidationError, match="requires record_count and ready_at"):
        DatasetSnapshot.model_validate(snapshot_payload(status=DatasetSnapshotStatus.ready))

    snapshot = DatasetSnapshot.model_validate(
        snapshot_payload(
            status=DatasetSnapshotStatus.ready,
            record_count=3,
            ready_at=CREATED_AT,
        )
    )

    assert snapshot.record_count == 3
    assert snapshot.ready_at == CREATED_AT


def test_failed_snapshot_requires_diagnostic_without_success_metadata() -> None:
    with pytest.raises(ValidationError, match="requires a failure diagnostic"):
        DatasetSnapshot.model_validate(snapshot_payload(status=DatasetSnapshotStatus.failed))
    with pytest.raises(ValidationError, match="only a ready snapshot may have ready_at"):
        DatasetSnapshot.model_validate(
            snapshot_payload(
                status=DatasetSnapshotStatus.failed,
                ready_at=CREATED_AT,
                failure_diagnostic="invalid TEI",
            )
        )

    snapshot = DatasetSnapshot.model_validate(
        snapshot_payload(
            status=DatasetSnapshotStatus.failed,
            failure_diagnostic="invalid TEI",
        )
    )

    assert snapshot.failure_diagnostic == "invalid TEI"


def test_person_record_preserves_snapshot_scoped_source_fields() -> None:
    person = PersonRecord(
        id=PERSON_ID,
        dataset_snapshot_id=SNAPSHOT_ID,
        tei_id="person-1",
        surname="Example",
        forenames=["Anna"],
        birth="1900",
        death=None,
        note="Synthetic fixture",
        alt_names=["A. Example"],
        gnd_id="123456789",
        external_ids={"wikidata": "Q1"},
        created_at=CREATED_AT,
    )

    assert person.model_dump(mode="json") == {
        "tei_id": "person-1",
        "surname": "Example",
        "forenames": ["Anna"],
        "birth": "1900",
        "death": None,
        "note": "Synthetic fixture",
        "alt_names": ["A. Example"],
        "gnd_id": "123456789",
        "external_ids": {"wikidata": "Q1"},
        "id": str(PERSON_ID),
        "dataset_snapshot_id": str(SNAPSHOT_ID),
        "created_at": "2026-08-13T10:00:00Z",
    }
