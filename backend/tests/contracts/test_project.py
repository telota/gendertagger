from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from gendertagger.models.lifecycle import DatasetSnapshotStatus
from gendertagger.models.person import PersonEvent, PersonNameForm, PersonNameType, PersonRecord
from gendertagger.models.project import (
    DatasetSnapshot,
    DatasetSnapshotCreate,
    DatasetSnapshotStatistics,
    Project,
    ProjectCreate,
    ProjectWorkingAggregationUpdate,
    SnapshotGndStatistics,
    SnapshotImportConfig,
    SnapshotImportLimits,
    SnapshotImportRequest,
    SnapshotSourceGenderStatistics,
    SourceFormat,
    SourceManifestMember,
    SourceManifestV1,
    SourcePackaging,
    TabularImportProfile,
    TeiImportProfile,
)
from gendertagger.models.team import TeamSummary

PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
TEAM_ID = UUID("10000000-0000-0000-0000-000000000002")
USER_ID = UUID("10000000-0000-0000-0000-000000000003")
SNAPSHOT_ID = UUID("20000000-0000-0000-0000-000000000001")
ARTIFACT_ID = UUID("30000000-0000-0000-0000-000000000001")
PERSON_ID = UUID("40000000-0000-0000-0000-000000000001")
AGGREGATION_ID = UUID("50000000-0000-0000-0000-000000000001")
SHA256 = "a" * 64
CREATED_AT = datetime(2026, 8, 13, 10, 0, tzinfo=UTC)


def snapshot_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": SNAPSHOT_ID,
        "project_id": PROJECT_ID,
        "source_artifact_id": ARTIFACT_ID,
        "source_sha256": SHA256,
        "parser_version": "tei_parser_v3",
        "import_config": {"profile": TeiImportProfile.tei_p5_person_register.value},
        "status": DatasetSnapshotStatus.pending,
        "record_count": None,
        "ready_at": None,
        "failure_diagnostic": None,
        "created_at": CREATED_AT,
    }
    payload.update(overrides)
    return payload


def team_summary() -> TeamSummary:
    return TeamSummary(
        id=TEAM_ID,
        slug="editorial-team",
        display_name="Editorial team",
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )


def test_project_create_requires_team_and_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="display_name must not be blank"):
        ProjectCreate(slug="edition", display_name="  ", team_id=TEAM_ID)
    with pytest.raises(ValidationError, match="Field required"):
        ProjectCreate.model_validate({"slug": "edition", "display_name": "Edition"})
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ProjectCreate.model_validate(
            {
                "slug": "edition",
                "display_name": "Edition",
                "team_id": TEAM_ID,
                "unexpected": True,
            }
        )


def test_project_working_aggregation_defaults_to_none_and_is_settable() -> None:
    without_pointer = Project(
        id=PROJECT_ID,
        slug="edition",
        display_name="Edition",
        team=team_summary(),
        manager_user_id=USER_ID,
        created_by_user_id=USER_ID,
        created_at=CREATED_AT,
    )
    with_pointer = without_pointer.model_copy(
        update={"working_aggregation_execution_id": AGGREGATION_ID}
    )

    assert without_pointer.working_aggregation_execution_id is None
    assert with_pointer.working_aggregation_execution_id == AGGREGATION_ID


def test_project_working_aggregation_update_accepts_a_pointer_or_null() -> None:
    assert (
        ProjectWorkingAggregationUpdate(
            aggregation_execution_id=AGGREGATION_ID
        ).aggregation_execution_id
        == AGGREGATION_ID
    )
    assert ProjectWorkingAggregationUpdate().aggregation_execution_id is None
    assert (
        ProjectWorkingAggregationUpdate(aggregation_execution_id=None).aggregation_execution_id
        is None
    )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ProjectWorkingAggregationUpdate.model_validate({"unexpected": True})


def test_snapshot_import_request_defaults_to_tei_without_exposing_a_profile() -> None:
    command = SnapshotImportRequest()

    assert command.model_dump(mode="json") == {
        "source_format": SourceFormat.tei.value,
        "packaging": SourcePackaging.single.value,
    }
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SnapshotImportRequest.model_validate({"profile": "unsupported_profile"})
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SnapshotImportRequest.model_validate({"unknown_option": True})


def test_snapshot_import_request_restricts_tabular_sources_to_single_packaging() -> None:
    tei_bundle = SnapshotImportRequest(packaging=SourcePackaging.tar_gz)
    tabular = SnapshotImportRequest(source_format=SourceFormat.csv)

    assert tei_bundle.packaging is SourcePackaging.tar_gz
    assert tabular.source_format is SourceFormat.csv
    with pytest.raises(ValidationError, match="packaging='single'"):
        SnapshotImportRequest(
            source_format=SourceFormat.xlsx,
            packaging=SourcePackaging.zip,
        )


def test_source_manifest_has_deterministic_bytes_and_safe_unique_names() -> None:
    manifest = SourceManifestV1(
        source_format=SourceFormat.tei,
        packaging=SourcePackaging.loose,
        members=(
            SourceManifestMember(
                logical_name="register/Ä.xml",
                sha256="a" * 64,
                byte_size=10,
                media_type="application/tei+xml",
            ),
        ),
    )

    assert manifest.canonical_bytes() == (
        b'{"members":[{"byte_size":10,"logical_name":"register/'
        + "Ä".encode()
        + b'.xml","media_type":"application/tei+xml","sha256":"'
        + b"a" * 64
        + b'"}],"packaging":"loose","source_format":"tei","version":1}'
    )
    assert SourceManifestV1.model_validate_json(manifest.canonical_bytes()) == manifest

    member = manifest.members[0]
    with pytest.raises(ValidationError, match="must be unique"):
        SourceManifestV1(
            source_format=SourceFormat.tei,
            packaging=SourcePackaging.loose,
            members=(
                member,
                member.model_copy(update={"logical_name": "REGISTER/ä.XML"}),
            ),
        )
    with pytest.raises(ValidationError, match="basenames must be unique"):
        SourceManifestV1(
            source_format=SourceFormat.tei,
            packaging=SourcePackaging.loose,
            members=(
                member.model_copy(update={"logical_name": "one/A.xml"}),
                member.model_copy(update={"logical_name": "two/a.XML"}),
            ),
        )
    with pytest.raises(ValidationError, match="unsafe path segment"):
        SourceManifestMember(
            logical_name="../register.xml",
            sha256="a" * 64,
            byte_size=10,
            media_type="application/tei+xml",
        )
    with pytest.raises(ValidationError, match="control character"):
        SourceManifestMember(
            logical_name="register\u202e.xml",
            sha256="a" * 64,
            byte_size=10,
            media_type="application/tei+xml",
        )


def test_snapshot_import_config_freezes_resolved_positive_limits() -> None:
    limits = SnapshotImportLimits(
        max_member_count=100,
        max_member_expanded_bytes=10_000,
        max_total_expanded_bytes=20_000,
        max_compression_ratio=20,
        max_record_count=1_000,
        max_cell_bytes=10_000,
    )
    config = SnapshotImportConfig(
        profile=TeiImportProfile.tei_p5_person_register,
        limits=limits,
    )

    assert config.profile is TeiImportProfile.tei_p5_person_register
    assert config.limits.max_record_count == 1_000
    with pytest.raises(ValidationError):
        SnapshotImportLimits.model_validate(
            limits.model_copy(update={"max_compression_ratio": 1}).model_dump()
        )


@pytest.mark.parametrize(
    ("source_format", "profile"),
    [
        (SourceFormat.tei, TabularImportProfile.tei_equivalent_person_register_v1),
        (SourceFormat.json, TeiImportProfile.tei_p5_person_register),
    ],
)
def test_snapshot_import_config_rejects_mismatched_derived_profile(
    source_format: SourceFormat,
    profile: TeiImportProfile | TabularImportProfile,
) -> None:
    with pytest.raises(ValidationError, match="provenance requires"):
        SnapshotImportConfig(
            source_format=source_format,
            profile=profile,
            limits=SnapshotImportLimits(),
        )


@pytest.mark.parametrize("slug", ["Uppercase", "two_words", "-leading", "trailing-"])
def test_project_create_rejects_noncanonical_slug(slug: str) -> None:
    with pytest.raises(ValidationError):
        ProjectCreate(slug=slug, display_name="Edition", team_id=TEAM_ID)


def test_snapshot_create_requires_json_compatible_config_and_sha256() -> None:
    with pytest.raises(ValidationError):
        DatasetSnapshotCreate(
            project_id=PROJECT_ID,
            source_artifact_id=ARTIFACT_ID,
            source_sha256="not-a-sha256",
            parser_version="tei_parser_v3",
        )
    with pytest.raises(ValidationError):
        DatasetSnapshotCreate.model_validate(
            {
                "project_id": PROJECT_ID,
                "source_artifact_id": ARTIFACT_ID,
                "source_sha256": SHA256,
                "parser_version": "tei_parser_v3",
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
    with pytest.raises(ValidationError, match="only a failed snapshot may have a failure class"):
        DatasetSnapshot.model_validate(snapshot_payload(failure_class="TeiImportError"))


def test_snapshot_statistics_require_complete_person_level_partitions() -> None:
    statistics = DatasetSnapshotStatistics(
        dataset_snapshot_id=SNAPSHOT_ID,
        total_person_count=3,
        source_gender=SnapshotSourceGenderStatistics(
            with_element_count=2,
            without_element_count=1,
            male_count=0,
            female_count=1,
            unknown_count=0,
            institution_count=0,
            other_or_multiple_count=1,
        ),
        gnd=SnapshotGndStatistics(
            with_reference_count=1,
            without_reference_count=2,
            with_reference_and_source_gender_count=1,
        ),
    )

    assert statistics.source_gender is not None
    assert statistics.source_gender.with_element_count == 2
    with pytest.raises(ValidationError, match="distribution"):
        SnapshotSourceGenderStatistics(
            with_element_count=2,
            without_element_count=1,
            male_count=0,
            female_count=1,
            unknown_count=0,
            institution_count=0,
            other_or_multiple_count=0,
        )
    with pytest.raises(ValidationError, match="GND coverage"):
        DatasetSnapshotStatistics(
            dataset_snapshot_id=SNAPSHOT_ID,
            total_person_count=3,
            source_gender=None,
            gnd=SnapshotGndStatistics(
                with_reference_count=1,
                without_reference_count=1,
            ),
        )


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
        events=[PersonEvent(type="wedding", when="1820", note="In Berlin")],
        alt_names=["A. Example"],
        name_forms=[
            PersonNameForm(
                type=PersonNameType.regular,
                surname="Example",
                forenames=["Anna"],
            ),
            PersonNameForm(
                type=PersonNameType.alternative,
                subtype="pseudonym",
                name="A. Example",
            ),
        ],
        gnd_id="123456789",
        external_ids={"wikidata": "Q1"},
        source_member_name="register.xml",
        source_record_locator="xml:id:person-1",
        created_at=CREATED_AT,
    )

    assert person.model_dump(mode="json") == {
        "tei_id": "person-1",
        "surname": "Example",
        "forenames": ["Anna"],
        "birth": "1900",
        "death": None,
        "note": "Synthetic fixture",
        "events": [{"type": "wedding", "when": "1820", "note": "In Berlin"}],
        "alt_names": ["A. Example"],
        "name_forms": [
            {
                "type": "reg",
                "subtype": None,
                "name": None,
                "surname": "Example",
                "forenames": ["Anna"],
            },
            {
                "type": "alt",
                "subtype": "pseudonym",
                "name": "A. Example",
                "surname": None,
                "forenames": [],
            },
        ],
        "gnd_id": "123456789",
        "external_ids": {"wikidata": "Q1"},
        "id": str(PERSON_ID),
        "dataset_snapshot_id": str(SNAPSHOT_ID),
        "source_member_name": "register.xml",
        "source_record_locator": "xml:id:person-1",
        "created_at": "2026-08-13T10:00:00Z",
    }
