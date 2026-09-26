from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import JsonValue
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from tests.factories import tei_person_input
from tests.seeding import (
    legacy_snapshot_statistics,
    seed_pending_snapshot,
    seed_project,
    seed_ready_snapshot,
    seed_run,
    session_repositories,
)

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.repositories.aggregation_repository import SqlAlchemyAggregationRepository
from gendertagger.db.repositories.artifact_repository import SqlAlchemyArtifactRepository
from gendertagger.db.repositories.project_repository import SqlAlchemyProjectRepository
from gendertagger.db.repositories.review_repository import SqlAlchemyReviewRepository
from gendertagger.db.repositories.run_repository import SqlAlchemyRunRepository
from gendertagger.db.repositories.user_repository import SqlAlchemyUserRepository
from gendertagger.db.rows.aggregations import AggregatedResultRow
from gendertagger.db.rows.artifacts import ArtifactRow
from gendertagger.db.rows.executions import MethodExecutionRow, PredictionRow
from gendertagger.db.rows.projects import (
    DatasetSnapshotRow,
    PersonExternalIdRow,
    PersonRecordRow,
    SnapshotSourceMemberRow,
)
from gendertagger.db.rows.reviews import AnnotationRow
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.models.aggregation import (
    AggregatedResult,
    AggregationExecutionCreate,
    AggregationOutcome,
    AggregationResultWrite,
    ReferenceAggregationResult,
    VoteCounts,
)
from gendertagger.models.artifact import Artifact, ArtifactCreate
from gendertagger.models.classification import (
    AgreementTier,
    CanonicalLabel,
    CertaintyTier,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.lifecycle import (
    AggregationExecutionStatus,
    DatasetSnapshotStatus,
    MethodExecutionStatus,
    RunStatus,
    TaskBatchStatus,
)
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import (
    ImportedPerson,
    PersonEvent,
    PersonInput,
    PersonNameForm,
    PersonNameType,
    PersonRecord,
)
from gendertagger.models.project import (
    DatasetSnapshotCreate,
    Project,
    SnapshotImportConfig,
    SnapshotImportLimits,
    SnapshotSourceMemberCreate,
    SourceFormat,
    SourcePackaging,
    TabularImportProfile,
    TeiImportProfile,
)
from gendertagger.models.review import AnnotationCreate, ReviewAction, ReviewWorkflowState
from gendertagger.models.run import (
    MethodExecutionCreate,
    MethodExecutionResultFilter,
    MethodExecutionResultState,
    Prediction,
    PredictionWrite,
    RunCreate,
    TaskBatchPlan,
)
from gendertagger.models.user import User, UserCreate
from gendertagger.services.ports.artifact_repository import AmbiguousArtifactError
from gendertagger.services.ports.persistence_errors import (
    ImmutableResourceError,
    InvalidResourceStateError,
    ResourceNotFoundError,
    ReviewConflictError,
)
from gendertagger.services.ports.run_repository import MethodExecutionResultCursor

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

TEST_IMPORT_LIMITS = SnapshotImportLimits(
    max_member_count=8,
    max_member_expanded_bytes=1_000_000,
    max_total_expanded_bytes=2_000_000,
    max_compression_ratio=100.0,
    max_record_count=10_000,
    max_cell_bytes=1_000_000,
)


def modern_import_config(
    *,
    source_format: SourceFormat = SourceFormat.tei,
    packaging: SourcePackaging = SourcePackaging.single,
    profile: TeiImportProfile | TabularImportProfile = (TeiImportProfile.tei_p5_person_register),
) -> dict[str, JsonValue]:
    return SnapshotImportConfig(
        source_format=source_format,
        packaging=packaging,
        profile=profile,
        limits=TEST_IMPORT_LIMITS,
    ).model_dump(mode="json")


def modern_parser_version(
    *,
    source_format: SourceFormat = SourceFormat.tei,
    packaging: SourcePackaging = SourcePackaging.single,
    profile: TeiImportProfile | TabularImportProfile = (TeiImportProfile.tei_p5_person_register),
) -> str:
    config = SnapshotImportConfig.model_validate(
        modern_import_config(
            source_format=source_format,
            packaging=packaging,
            profile=profile,
        )
    )
    return version_for_snapshot_import(config)


def _mutate_and_flush(session: Session, mutation: Callable[[], None]) -> None:
    mutation()
    session.flush()


def assert_database_rejects_mutation(
    session: Session,
    mutation: Callable[[], None],
) -> None:
    with pytest.raises(DBAPIError) as error, session.begin_nested():
        _mutate_and_flush(session, mutation)
    assert getattr(error.value.orig, "sqlstate", None) == "55000"
    session.expire_all()


def test_artifact_content_identity_rejects_ambiguous_records(db_session: Session) -> None:
    artifacts = SqlAlchemyArtifactRepository(db_session)
    for storage_uri in ("file:///first.sqlite3", "file:///second.sqlite3"):
        artifacts.add_artifact(
            ArtifactCreate(
                logical_type="test_lookup",
                storage_uri=storage_uri,
                sha256="e" * 64,
                byte_size=1,
                media_type="application/vnd.sqlite3",
            )
        )

    with pytest.raises(AmbiguousArtifactError, match="is ambiguous"):
        artifacts.get_artifact_by_sha256("test_lookup", "e" * 64)


@pytest.mark.parametrize(
    ("profile", "person", "reason"),
    [
        (
            TeiImportProfile.tei_p5_person_register,
            PersonInput(tei_id="p1", surname="Example"),
            "name_forms",
        ),
        (
            TabularImportProfile.tei_equivalent_person_register_v1,
            PersonInput(tei_id="p1", surname="Example"),
            "name_forms",
        ),
    ],
)
def test_person_records_require_fields_matching_the_snapshot_profile(
    db_session: Session,
    profile: TeiImportProfile | TabularImportProfile,
    person: PersonInput,
    reason: str,
) -> None:
    projects = SqlAlchemyProjectRepository(db_session)
    project = seed_project(
        session_repositories(db_session),
        slug_prefix="profile",
        display_name="Profile consistency fixture",
    )
    source_format = (
        SourceFormat.csv if isinstance(profile, TabularImportProfile) else SourceFormat.tei
    )
    artifacts = SqlAlchemyArtifactRepository(db_session)
    source_artifact = artifacts.add_artifact(
        ArtifactCreate(
            logical_type=f"source_{source_format.value}",
            storage_uri=f"file:///synthetic/{profile.value}.{source_format.value}",
            sha256="e" * 64,
            byte_size=42,
            media_type="text/csv" if source_format is SourceFormat.csv else "application/xml",
            project_id=project.id,
        )
    )
    import_config = modern_import_config(source_format=source_format, profile=profile)
    parser_version = modern_parser_version(source_format=source_format, profile=profile)
    snapshot = projects.add_snapshot(
        DatasetSnapshotCreate(
            project_id=project.id,
            source_artifact_id=source_artifact.id,
            source_sha256=source_artifact.sha256,
            parser_version=parser_version,
            import_config=import_config,
        )
    )
    projects.add_snapshot_source_members(
        snapshot.id,
        [
            SnapshotSourceMemberCreate(
                artifact_id=source_artifact.id,
                ordinal=0,
                logical_name="source.xml",
                sha256=source_artifact.sha256,
                byte_size=source_artifact.byte_size,
                media_type=source_artifact.media_type,
            )
        ],
    )
    assert projects.claim_snapshot_import(snapshot.id) is not None

    with pytest.raises(InvalidResourceStateError, match=reason):
        projects.add_imported_person_records(
            snapshot.id,
            [
                ImportedPerson(
                    person=person,
                    source_member_name="source.xml",
                    source_record_locator="1",
                )
            ],
        )

    assert (
        db_session.scalar(
            select(func.count())
            .select_from(PersonRecordRow)
            .where(PersonRecordRow.dataset_snapshot_id == snapshot.id)
        )
        == 0
    )


def test_modern_snapshot_requires_complete_config_and_primary_artifact_provenance(
    db_session: Session,
) -> None:
    projects = SqlAlchemyProjectRepository(db_session)
    artifacts = SqlAlchemyArtifactRepository(db_session)
    repositories = session_repositories(db_session)
    project = seed_project(
        repositories,
        slug_prefix="modern-primary",
        display_name="Modern primary artifact fixture",
    )
    other_project = seed_project(
        repositories,
        slug_prefix="modern-primary-other",
        display_name="Other primary artifact fixture",
    )
    primary = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri="file:///synthetic/primary.xml",
            sha256="1" * 64,
            byte_size=42,
            media_type="application/tei+xml",
            project_id=project.id,
        )
    )
    cross_project = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri="file:///synthetic/cross-project.xml",
            sha256="2" * 64,
            byte_size=42,
            media_type="application/tei+xml",
            project_id=other_project.id,
        )
    )
    wrong_type = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_csv",
            storage_uri="file:///synthetic/wrong-type.csv",
            sha256="3" * 64,
            byte_size=42,
            media_type="text/csv",
            project_id=project.id,
        )
    )

    with pytest.raises(InvalidResourceStateError, match="complete supported"):
        projects.add_snapshot(
            DatasetSnapshotCreate(
                project_id=project.id,
                source_artifact_id=primary.id,
                source_sha256=primary.sha256,
                parser_version=modern_parser_version(),
                import_config={
                    "source_format": SourceFormat.tei.value,
                    "packaging": SourcePackaging.single.value,
                    "profile": TeiImportProfile.tei_p5_person_register.value,
                },
            )
        )
    with pytest.raises(InvalidResourceStateError, match="parser version"):
        projects.add_snapshot(
            DatasetSnapshotCreate(
                project_id=project.id,
                source_artifact_id=primary.id,
                source_sha256=primary.sha256,
                parser_version="tei_parser_v3",
                import_config=modern_import_config(),
            )
        )
    with pytest.raises(ResourceNotFoundError, match="does not exist"):
        projects.add_snapshot(
            DatasetSnapshotCreate(
                project_id=project.id,
                source_artifact_id=uuid4(),
                source_sha256="4" * 64,
                parser_version=modern_parser_version(),
                import_config=modern_import_config(),
            )
        )
    with pytest.raises(InvalidResourceStateError, match="different project"):
        projects.add_snapshot(
            DatasetSnapshotCreate(
                project_id=project.id,
                source_artifact_id=cross_project.id,
                source_sha256=cross_project.sha256,
                parser_version=modern_parser_version(),
                import_config=modern_import_config(),
            )
        )
    with pytest.raises(InvalidResourceStateError, match="checksum"):
        projects.add_snapshot(
            DatasetSnapshotCreate(
                project_id=project.id,
                source_artifact_id=primary.id,
                source_sha256="5" * 64,
                parser_version=modern_parser_version(),
                import_config=modern_import_config(),
            )
        )
    with pytest.raises(InvalidResourceStateError, match="logical type"):
        projects.add_snapshot(
            DatasetSnapshotCreate(
                project_id=project.id,
                source_artifact_id=wrong_type.id,
                source_sha256=wrong_type.sha256,
                parser_version=modern_parser_version(),
                import_config=modern_import_config(),
            )
        )


def test_modern_non_loose_source_member_must_be_primary_artifact(
    db_session: Session,
) -> None:
    projects = SqlAlchemyProjectRepository(db_session)
    artifacts = SqlAlchemyArtifactRepository(db_session)
    project = seed_project(
        session_repositories(db_session),
        slug_prefix="modern-member",
        display_name="Modern source member fixture",
    )
    primary = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri="file:///synthetic/primary.xml",
            sha256="6" * 64,
            byte_size=42,
            media_type="application/tei+xml",
            project_id=project.id,
        )
    )
    other = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri="file:///synthetic/other.xml",
            sha256="7" * 64,
            byte_size=43,
            media_type="application/tei+xml",
            project_id=project.id,
        )
    )
    snapshot = projects.add_snapshot(
        DatasetSnapshotCreate(
            project_id=project.id,
            source_artifact_id=primary.id,
            source_sha256=primary.sha256,
            parser_version=modern_parser_version(),
            import_config=modern_import_config(),
        )
    )

    with pytest.raises(InvalidResourceStateError, match="primary source artifact"):
        projects.add_snapshot_source_members(
            snapshot.id,
            [
                SnapshotSourceMemberCreate(
                    artifact_id=other.id,
                    ordinal=0,
                    logical_name="other.xml",
                    sha256=other.sha256,
                    byte_size=other.byte_size,
                    media_type=other.media_type,
                )
            ],
        )

    projects.add_snapshot_source_members(
        snapshot.id,
        [
            SnapshotSourceMemberCreate(
                artifact_id=primary.id,
                ordinal=0,
                logical_name="primary.xml",
                sha256=primary.sha256,
                byte_size=primary.byte_size,
                media_type=primary.media_type,
            )
        ],
    )
    assert projects.claim_snapshot_import(snapshot.id) is not None
    ready = projects.complete_snapshot_import(
        snapshot.id,
        statistics=legacy_snapshot_statistics(snapshot.id, []),
        ready_at=datetime.now(UTC),
    )

    assert ready.record_count == 0


def test_ready_transition_rejects_missing_or_malformed_modern_source_sets(
    db_session: Session,
) -> None:
    projects = SqlAlchemyProjectRepository(db_session)
    artifacts = SqlAlchemyArtifactRepository(db_session)
    project = seed_project(
        session_repositories(db_session),
        slug_prefix="modern-ready",
        display_name="Modern ready transition fixture",
    )
    primary = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri="file:///synthetic/ready-primary.xml",
            sha256="8" * 64,
            byte_size=42,
            media_type="application/tei+xml",
            project_id=project.id,
        )
    )
    other = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri="file:///synthetic/ready-other.xml",
            sha256="9" * 64,
            byte_size=43,
            media_type="application/tei+xml",
            project_id=project.id,
        )
    )
    missing_members = projects.add_snapshot(
        DatasetSnapshotCreate(
            project_id=project.id,
            source_artifact_id=primary.id,
            source_sha256=primary.sha256,
            parser_version=modern_parser_version(),
            import_config=modern_import_config(),
        )
    )
    assert projects.claim_snapshot_import(missing_members.id) is not None
    with pytest.raises(InvalidResourceStateError, match="complete source-member set"):
        projects.complete_snapshot_import(
            missing_members.id,
            statistics=legacy_snapshot_statistics(missing_members.id, []),
            ready_at=datetime.now(UTC),
        )

    wrong_primary = projects.add_snapshot(
        DatasetSnapshotCreate(
            project_id=project.id,
            source_artifact_id=primary.id,
            source_sha256=primary.sha256,
            parser_version=modern_parser_version(),
            import_config=modern_import_config(),
        )
    )
    db_session.add(
        SnapshotSourceMemberRow(
            dataset_snapshot_id=wrong_primary.id,
            artifact_id=other.id,
            ordinal=0,
            logical_name="other.xml",
            sha256=other.sha256,
            byte_size=other.byte_size,
            media_type=other.media_type,
        )
    )
    db_session.flush()
    assert projects.claim_snapshot_import(wrong_primary.id) is not None
    with pytest.raises(InvalidResourceStateError, match="primary source artifact"):
        projects.complete_snapshot_import(
            wrong_primary.id,
            statistics=legacy_snapshot_statistics(wrong_primary.id, []),
            ready_at=datetime.now(UTC),
        )

    manifest = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_manifest",
            storage_uri="file:///synthetic/ready-manifest.json",
            sha256="a" * 64,
            byte_size=100,
            media_type="application/vnd.gendertagger.source-manifest+json",
            project_id=project.id,
        )
    )
    ordinal_gap = projects.add_snapshot(
        DatasetSnapshotCreate(
            project_id=project.id,
            source_artifact_id=manifest.id,
            source_sha256=manifest.sha256,
            parser_version=modern_parser_version(packaging=SourcePackaging.loose),
            import_config=modern_import_config(packaging=SourcePackaging.loose),
        )
    )
    db_session.add(
        SnapshotSourceMemberRow(
            dataset_snapshot_id=ordinal_gap.id,
            artifact_id=other.id,
            ordinal=1,
            logical_name="other.xml",
            sha256=other.sha256,
            byte_size=other.byte_size,
            media_type=other.media_type,
        )
    )
    db_session.flush()
    assert projects.claim_snapshot_import(ordinal_gap.id) is not None
    with pytest.raises(InvalidResourceStateError, match="contiguous"):
        projects.complete_snapshot_import(
            ordinal_gap.id,
            statistics=legacy_snapshot_statistics(ordinal_gap.id, []),
            ready_at=datetime.now(UTC),
        )


def test_ready_transition_rechecks_modern_parser_provenance(db_session: Session) -> None:
    projects = SqlAlchemyProjectRepository(db_session)
    artifacts = SqlAlchemyArtifactRepository(db_session)
    project = seed_project(
        session_repositories(db_session),
        slug_prefix="modern-ready-parser",
        display_name="Modern ready parser fixture",
    )
    primary = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri="file:///synthetic/ready-parser.xml",
            sha256="c" * 64,
            byte_size=42,
            media_type="application/tei+xml",
            project_id=project.id,
        )
    )
    snapshot = projects.add_snapshot(
        DatasetSnapshotCreate(
            project_id=project.id,
            source_artifact_id=primary.id,
            source_sha256=primary.sha256,
            parser_version=modern_parser_version(),
            import_config=modern_import_config(),
        )
    )
    projects.add_snapshot_source_members(
        snapshot.id,
        [
            SnapshotSourceMemberCreate(
                artifact_id=primary.id,
                ordinal=0,
                logical_name="ready-parser.xml",
                sha256=primary.sha256,
                byte_size=primary.byte_size,
                media_type=primary.media_type,
            )
        ],
    )
    row = db_session.get(DatasetSnapshotRow, snapshot.id)
    assert row is not None
    row.parser_version = "tei_parser_v3"
    db_session.flush()
    assert projects.claim_snapshot_import(snapshot.id) is not None

    with pytest.raises(InvalidResourceStateError, match="parser version"):
        projects.complete_snapshot_import(
            snapshot.id,
            statistics=legacy_snapshot_statistics(snapshot.id, []),
            ready_at=datetime.now(UTC),
        )


def test_legacy_ready_snapshot_derives_gnd_statistics(db_session: Session) -> None:
    repositories = session_repositories(db_session)
    project = seed_project(
        repositories,
        slug_prefix="legacy-statistics",
        display_name="Legacy statistics fixture",
    )
    snapshot = seed_pending_snapshot(repositories, project.id)
    assert repositories.projects.claim_snapshot_import(snapshot.id) is not None
    repositories.projects.add_imported_person_records(
        snapshot.id,
        [
            ImportedPerson(
                person=PersonInput(
                    tei_id="p1",
                    surname="Example",
                    name_forms=[PersonNameForm(type=PersonNameType.regular, surname="Example")],
                    gnd_id="123456789",
                ),
                source_member_name="source.xml",
                source_record_locator="xml:id:p1",
            )
        ],
    )
    row = db_session.get(DatasetSnapshotRow, snapshot.id)
    assert row is not None
    row.record_count = 1
    row.ready_at = datetime.now(UTC)
    row.status = DatasetSnapshotStatus.ready
    db_session.flush()

    statistics = repositories.projects.get_snapshot_statistics(snapshot.id)

    assert statistics is not None
    assert statistics.total_person_count == 1
    assert statistics.source_gender is None
    assert statistics.gnd.with_reference_count == 1
    assert statistics.gnd.without_reference_count == 0
    assert statistics.gnd.with_reference_and_source_gender_count is None


def test_source_members_and_imported_person_provenance_round_trip(db_session: Session) -> None:
    artifacts = SqlAlchemyArtifactRepository(db_session)
    projects = SqlAlchemyProjectRepository(db_session)
    project = seed_project(
        session_repositories(db_session),
        slug_prefix="source-members",
        display_name="Source members fixture",
    )
    manifest_artifact = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_manifest",
            storage_uri="file:///synthetic/manifest.json",
            sha256="a" * 64,
            byte_size=100,
            media_type="application/vnd.gendertagger.source-manifest+json",
            project_id=project.id,
        )
    )
    first_artifact = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri="file:///synthetic/A.xml",
            sha256="b" * 64,
            byte_size=20,
            media_type="application/tei+xml",
            project_id=project.id,
        )
    )
    second_artifact = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri="file:///synthetic/B.xml",
            sha256="c" * 64,
            byte_size=30,
            media_type="application/tei+xml",
            project_id=project.id,
        )
    )
    snapshot = projects.add_snapshot(
        DatasetSnapshotCreate(
            project_id=project.id,
            source_artifact_id=manifest_artifact.id,
            source_sha256=manifest_artifact.sha256,
            parser_version=modern_parser_version(packaging=SourcePackaging.loose),
            import_config=modern_import_config(packaging=SourcePackaging.loose),
        )
    )
    with pytest.raises(ValueError, match="basenames must be unique"):
        projects.add_snapshot_source_members(
            snapshot.id,
            [
                SnapshotSourceMemberCreate(
                    artifact_id=first_artifact.id,
                    ordinal=0,
                    logical_name="one/A.xml",
                    sha256=first_artifact.sha256,
                    byte_size=first_artifact.byte_size,
                    media_type=first_artifact.media_type,
                ),
                SnapshotSourceMemberCreate(
                    artifact_id=second_artifact.id,
                    ordinal=1,
                    logical_name="two/a.XML",
                    sha256=second_artifact.sha256,
                    byte_size=second_artifact.byte_size,
                    media_type=second_artifact.media_type,
                ),
            ],
        )
    persisted_members = projects.add_snapshot_source_members(
        snapshot.id,
        [
            SnapshotSourceMemberCreate(
                artifact_id=second_artifact.id,
                ordinal=1,
                logical_name="B.xml",
                sha256=second_artifact.sha256,
                byte_size=second_artifact.byte_size,
                media_type=second_artifact.media_type,
            ),
            SnapshotSourceMemberCreate(
                artifact_id=first_artifact.id,
                ordinal=0,
                logical_name="A.xml",
                sha256=first_artifact.sha256,
                byte_size=first_artifact.byte_size,
                media_type=first_artifact.media_type,
            ),
        ],
    )

    assert [member.logical_name for member in persisted_members] == ["A.xml", "B.xml"]
    assert projects.list_snapshot_source_members(snapshot.id) == persisted_members

    assert projects.claim_snapshot_import(snapshot.id) is not None
    with pytest.raises(InvalidResourceStateError, match="not attached"):
        projects.add_imported_person_records(
            snapshot.id,
            [
                ImportedPerson(
                    person=PersonInput(
                        tei_id="missing-source",
                        surname="Missing",
                        name_forms=[PersonNameForm(type=PersonNameType.regular, surname="Missing")],
                    ),
                    source_member_name="C.xml",
                    source_record_locator="xml:id:missing-source",
                )
            ],
        )
    assert (
        projects.add_imported_person_records(
            snapshot.id,
            [
                ImportedPerson(
                    person=PersonInput(
                        tei_id="p1",
                        surname="Example",
                        name_forms=[PersonNameForm(type=PersonNameType.regular, surname="Example")],
                        events=[PersonEvent(type="wedding", when="1820", note="Synthetic event")],
                    ),
                    source_member_name="A.xml",
                    source_record_locator="xml:id:p1",
                )
            ],
        )
        == 1
    )
    snapshot = projects.complete_snapshot_import(
        snapshot.id,
        statistics=legacy_snapshot_statistics(snapshot.id, [PersonInput(tei_id="p1")]),
        ready_at=datetime.now(UTC),
    )
    person = projects.get_person_record_by_tei_id(snapshot.id, "p1")

    assert person is not None
    assert person.source_member_name == "A.xml"
    assert person.source_record_locator == "xml:id:p1"
    assert person.events == [PersonEvent(type="wedding", when="1820", note="Synthetic event")]

    source_member_row = db_session.scalar(
        select(SnapshotSourceMemberRow).where(
            SnapshotSourceMemberRow.dataset_snapshot_id == snapshot.id,
            SnapshotSourceMemberRow.ordinal == 0,
        )
    )
    assert source_member_row is not None
    assert_database_rejects_mutation(
        db_session,
        lambda: setattr(source_member_row, "logical_name", "Changed.xml"),
    )

    archive_artifact = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_zip",
            storage_uri="file:///synthetic/register.zip",
            sha256="d" * 64,
            byte_size=50,
            media_type="application/zip",
            project_id=project.id,
        )
    )
    archive_snapshot = projects.add_snapshot(
        DatasetSnapshotCreate(
            project_id=project.id,
            source_artifact_id=archive_artifact.id,
            source_sha256=archive_artifact.sha256,
            parser_version=modern_parser_version(packaging=SourcePackaging.zip),
            import_config=modern_import_config(packaging=SourcePackaging.zip),
        )
    )
    projects.add_snapshot_source_members(
        archive_snapshot.id,
        [
            SnapshotSourceMemberCreate(
                artifact_id=archive_artifact.id,
                ordinal=0,
                logical_name="register.zip",
                sha256=archive_artifact.sha256,
                byte_size=archive_artifact.byte_size,
                media_type=archive_artifact.media_type,
            )
        ],
    )
    assert projects.claim_snapshot_import(archive_snapshot.id) is not None

    assert (
        projects.add_imported_person_records(
            archive_snapshot.id,
            [
                ImportedPerson(
                    person=PersonInput(
                        tei_id="archive-p1",
                        surname="Archive",
                        name_forms=[PersonNameForm(type=PersonNameType.regular, surname="Archive")],
                    ),
                    source_member_name="internal/A.xml",
                    source_record_locator="xml:id:archive-p1",
                )
            ],
        )
        == 1
    )


def test_domain_contracts_round_trip_without_orm_leak(db_session: Session) -> None:
    now = datetime.now(UTC)
    projects = SqlAlchemyProjectRepository(db_session)
    project = seed_project(
        session_repositories(db_session),
        slug_prefix="integration",
        display_name="Synthetic integration project",
    )
    artifacts = SqlAlchemyArtifactRepository(db_session)
    source_artifact = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri="file:///synthetic/source.xml",
            sha256="a" * 64,
            byte_size=42,
            media_type="application/tei+xml",
            metadata={"fixture": "synthetic"},
            project_id=project.id,
        )
    )
    snapshot = projects.add_snapshot(
        DatasetSnapshotCreate(
            project_id=project.id,
            source_artifact_id=source_artifact.id,
            source_sha256=source_artifact.sha256,
            parser_version=modern_parser_version(),
            import_config=modern_import_config(),
        )
    )
    projects.add_snapshot_source_members(
        snapshot.id,
        [
            SnapshotSourceMemberCreate(
                artifact_id=source_artifact.id,
                ordinal=0,
                logical_name="source.xml",
                sha256=source_artifact.sha256,
                byte_size=source_artifact.byte_size,
                media_type=source_artifact.media_type,
            )
        ],
    )
    assert projects.claim_snapshot_import(snapshot.id) is not None
    assert (
        projects.add_imported_person_records(
            snapshot.id,
            [
                ImportedPerson(
                    person=PersonInput(
                        tei_id="p1",
                        surname="Example",
                        forenames=["Anna"],
                        birth="1900",
                        death="1980",
                        note="Synthetic fixture",
                        alt_names=["Earlier Annette", "A. Example"],
                        name_forms=[
                            PersonNameForm(
                                type=PersonNameType.regular,
                                surname="Example",
                                forenames=["Anna"],
                            ),
                            PersonNameForm(
                                type=PersonNameType.alternative,
                                subtype="birthname",
                                surname="Earlier",
                                forenames=["Annette"],
                            ),
                            PersonNameForm(
                                type=PersonNameType.alternative,
                                name="A. Example",
                            ),
                        ],
                        gnd_id="123456789",
                        external_ids={"wikidata": "Q1"},
                    ),
                    source_member_name="source.xml",
                    source_record_locator="xml:id:p1",
                )
            ],
        )
        == 1
    )
    snapshot = projects.complete_snapshot_import(
        snapshot.id,
        statistics=legacy_snapshot_statistics(
            snapshot.id,
            [PersonInput(tei_id="p1", gnd_id="123456789")],
        ),
        ready_at=now,
    )
    person = projects.get_person_record_by_tei_id(snapshot.id, "p1")
    assert person is not None

    users = SqlAlchemyUserRepository(db_session)
    reviewer = users.add_user(UserCreate(display_name="Synthetic reviewer"))

    runs = SqlAlchemyRunRepository(db_session)
    run_config = RunConfig(
        methods=[MethodRunConfig(name=method_name) for method_name in REFERENCE_REQUIRED_METHODS]
    )
    run = runs.add_run(
        RunCreate(
            dataset_snapshot_id=snapshot.id,
            resolved_config=run_config,
            code_git_commit="abc123",
            application_version="0.0.0",
            python_version="3.13.14",
            dependency_lock_sha256="b" * 64,
        )
    )
    execution = runs.add_method_execution(
        MethodExecutionCreate(
            run_id=run.id,
            descriptor=MethodDescriptor(
                name="gender_guesser",
                implementation_version="1.0.0",
                normalization_version="gender_guesser_v1",
            ),
            resolved_config={"threshold": 0.5},
            queue_name="cpu",
            total_count=1,
        )
    )
    (batch,) = runs.create_task_batches(
        execution.id, [TaskBatchPlan(batch_index=0, record_offset=0, record_count=1)]
    )
    runs.mark_run_queued(run.id)
    runs.mark_run_started(run.id, started_at=now)
    runs.mark_execution_queued(execution.id)
    runs.mark_execution_started(execution.id, started_at=now)
    claimed_batch = runs.claim_batch(
        batch.id,
        method_execution_id=execution.id,
        worker_task_id="fixture-gender-guesser",
        started_at=now,
        attempt_count=1,
    )
    assert claimed_batch is not None
    prediction_result = PredictionResult(
        label=CanonicalLabel.unknown,
        status=PredictionStatus.success,
        method_confidence=0.75,
        raw_label="uncertain",
        raw_output={"label": "uncertain", "score": 0.75},
        metadata={
            "normalization_version": "gender_guesser_v1",
            "outcome_reason": "mapped_unknown",
        },
    )
    prediction_write = PredictionWrite(
        person_record_id=person.id,
        task_batch_id=batch.id,
        input_fingerprint="c" * 64,
        result=prediction_result,
    )
    assert runs.add_predictions(execution.id, [prediction_write]) == 1
    assert runs.add_predictions(execution.id, [prediction_write]) == 1
    conflicting_write = prediction_write.model_copy(
        update={"result": prediction_result.model_copy(update={"raw_label": "different"})}
    )
    with pytest.raises(ImmutableResourceError, match="different output or provenance"):
        runs.add_predictions(execution.id, [conflicting_write])
    runs.mark_batch_finished(
        batch.id,
        status=TaskBatchStatus.completed,
        finished_at=now,
        success_count=1,
    )
    runs.finalize_execution_if_complete(execution.id, finished_at=now)
    prediction_count = db_session.scalar(
        select(func.count())
        .select_from(PredictionRow)
        .where(
            PredictionRow.method_execution_id == execution.id,
            PredictionRow.person_record_id == person.id,
        )
    )
    assert prediction_count == 1
    prediction_id = db_session.scalar(
        select(PredictionRow.id).where(
            PredictionRow.method_execution_id == execution.id,
            PredictionRow.person_record_id == person.id,
        )
    )
    assert prediction_id is not None
    prediction = runs.get_prediction(prediction_id)
    assert prediction is not None

    execution_ids = [execution.id]
    for method_name in REFERENCE_REQUIRED_METHODS:
        if method_name == "gender_guesser":
            continue
        additional_execution = runs.add_method_execution(
            MethodExecutionCreate(
                run_id=run.id,
                descriptor=MethodDescriptor(
                    name=method_name,
                    implementation_version=f"{method_name}_v1",
                    normalization_version=f"{method_name}_v1",
                ),
                queue_name="cpu",
                total_count=1,
            )
        )
        execution_ids.append(additional_execution.id)
        (additional_batch,) = runs.create_task_batches(
            additional_execution.id,
            [TaskBatchPlan(batch_index=0, record_offset=0, record_count=1)],
        )
        runs.mark_execution_queued(additional_execution.id)
        runs.mark_execution_started(additional_execution.id, started_at=now)
        claimed_additional_batch = runs.claim_batch(
            additional_batch.id,
            method_execution_id=additional_execution.id,
            worker_task_id=f"fixture-{method_name}",
            started_at=now,
            attempt_count=1,
        )
        assert claimed_additional_batch is not None
        runs.add_predictions(
            additional_execution.id,
            [
                PredictionWrite(
                    person_record_id=person.id,
                    task_batch_id=additional_batch.id,
                    input_fingerprint="c" * 64,
                    result=PredictionResult(
                        label=None,
                        status=PredictionStatus.abstain,
                    ),
                )
            ],
        )
        runs.mark_batch_finished(
            additional_batch.id,
            status=TaskBatchStatus.completed,
            finished_at=now,
            abstain_count=1,
        )
        runs.finalize_execution_if_complete(additional_execution.id, finished_at=now)

    execution_rows = tuple(
        db_session.scalars(
            select(MethodExecutionRow).where(MethodExecutionRow.id.in_(execution_ids))
        )
    )
    assert len(execution_rows) == len(REFERENCE_REQUIRED_METHODS)
    assert all(row.status is MethodExecutionStatus.completed for row in execution_rows)
    runs.finalize_run_if_complete(run.id, finished_at=now)

    aggregations = SqlAlchemyAggregationRepository(db_session)
    aggregation = aggregations.add_aggregation(
        AggregationExecutionCreate(
            run_id=run.id,
            method_execution_ids=tuple(execution_ids),
        )
    )
    claimed_aggregation = aggregations.claim_aggregation(
        aggregation.id,
        started_at=now,
    )
    assert claimed_aggregation is not None
    scientific_result = ReferenceAggregationResult(
        outcome=AggregationOutcome.decided,
        label=CanonicalLabel.unknown,
        pooled_vote_counts=VoteCounts(unknown=1),
        agreement_score=1.0,
        agreement_tier=AgreementTier.single_rater,
        certainty_tier=CertaintyTier.uncertain,
    )
    assert (
        aggregations.add_results(
            aggregation.id,
            [
                AggregationResultWrite(
                    person_record_id=person.id,
                    result=scientific_result,
                    metadata={"strategy": "reference_v1"},
                )
            ],
        )
        == 1
    )
    aggregation = aggregations.mark_aggregation_finished(
        aggregation.id,
        status=AggregationExecutionStatus.completed,
        finished_at=now,
    )
    aggregated_result_id = db_session.scalar(
        select(AggregatedResultRow.id).where(
            AggregatedResultRow.aggregation_execution_id == aggregation.id,
            AggregatedResultRow.person_record_id == person.id,
        )
    )
    assert aggregated_result_id is not None
    aggregated_result = aggregations.get_result(aggregated_result_id)
    assert aggregated_result is not None

    reviews = SqlAlchemyReviewRepository(db_session)
    initial_state = reviews.get_review_state(snapshot.id, person.tei_id)
    assert initial_state is not None
    first_annotation = reviews.add_annotation(
        AnnotationCreate(
            snapshot_id=snapshot.id,
            tei_id=person.tei_id,
            action=ReviewAction.verify,
            label=CanonicalLabel.unknown,
            aggregated_result_id=aggregated_result.id,
            expected_revision=0,
        ),
        reviewer_user_id=reviewer.id,
    )
    with pytest.raises(ReviewConflictError) as conflict:
        reviews.add_annotation(
            AnnotationCreate(
                snapshot_id=snapshot.id,
                tei_id=person.tei_id,
                action=ReviewAction.defer,
                expected_revision=0,
            ),
            reviewer_user_id=reviewer.id,
        )
    second_annotation = reviews.add_annotation(
        AnnotationCreate(
            snapshot_id=snapshot.id,
            tei_id=person.tei_id,
            action=ReviewAction.correct,
            label=CanonicalLabel.female,
            comment="Synthetic correction",
            aggregated_result_id=aggregated_result.id,
            expected_revision=1,
        ),
        reviewer_user_id=reviewer.id,
    )
    review_state = reviews.get_review_state(snapshot.id, person.tei_id)
    assert review_state is not None

    assert isinstance(source_artifact, Artifact)
    assert isinstance(project, Project)
    assert isinstance(person, PersonRecord)
    assert isinstance(reviewer, User)
    assert isinstance(prediction, Prediction)
    assert isinstance(aggregated_result, AggregatedResult)
    assert snapshot.record_count == 1
    assert person.surname == "Example"
    assert person.forenames == ["Anna"]
    assert person.birth == "1900"
    assert person.death == "1980"
    assert person.note == "Synthetic fixture"
    assert person.alt_names == ["Earlier Annette", "A. Example"]
    assert person.name_forms == [
        PersonNameForm(
            type=PersonNameType.regular,
            surname="Example",
            forenames=["Anna"],
        ),
        PersonNameForm(
            type=PersonNameType.alternative,
            subtype="birthname",
            surname="Earlier",
            forenames=["Annette"],
        ),
        PersonNameForm(
            type=PersonNameType.alternative,
            name="A. Example",
        ),
    ]
    assert person.gnd_id == "123456789"
    assert person.external_ids == {"wikidata": "Q1"}
    assert run.config_sha256 == run_config.canonical_sha256()
    assert (
        prediction.model_dump(
            exclude={
                "id",
                "method_execution_id",
                "person_record_id",
                "task_batch_id",
                "input_fingerprint",
                "created_at",
            }
        )
        == prediction_result.model_dump()
    )
    assert aggregation.method_execution_ids == tuple(execution_ids)
    assert aggregated_result.pooled_vote_counts == VoteCounts(unknown=1)
    assert conflict.value.current_revision == 1
    assert second_annotation.supersedes_annotation_id == first_annotation.id
    assert review_state.revision == 2
    assert review_state.workflow_state is ReviewWorkflowState.reviewed
    assert artifacts.get_artifact(source_artifact.id) == source_artifact
    assert (
        artifacts.get_artifact_by_sha256(source_artifact.logical_type, source_artifact.sha256)
        == source_artifact
    )
    assert users.get_user(reviewer.id) == reviewer

    with pytest.raises(ImmutableResourceError, match="ready and immutable"):
        projects.add_imported_person_records(
            snapshot.id,
            [
                ImportedPerson(
                    person=PersonInput(tei_id="p2"),
                    source_member_name="source.xml",
                    source_record_locator="xml:id:p2",
                )
            ],
        )

    artifact_row = db_session.get(ArtifactRow, source_artifact.id)
    snapshot_row = db_session.get(DatasetSnapshotRow, snapshot.id)
    person_row = db_session.get(PersonRecordRow, person.id)
    external_id_row = db_session.scalar(
        select(PersonExternalIdRow).where(
            PersonExternalIdRow.person_record_id == person.id,
            PersonExternalIdRow.scheme == "gnd",
        )
    )
    prediction_row = db_session.get(PredictionRow, prediction.id)
    aggregated_result_row = db_session.get(AggregatedResultRow, aggregated_result.id)
    annotation_row = db_session.get(AnnotationRow, first_annotation.id)
    assert artifact_row is not None
    assert snapshot_row is not None
    assert person_row is not None
    assert external_id_row is not None
    assert prediction_row is not None
    assert aggregated_result_row is not None
    assert annotation_row is not None

    assert_database_rejects_mutation(
        db_session,
        lambda: setattr(artifact_row, "media_type", "text/plain"),
    )
    assert_database_rejects_mutation(
        db_session,
        lambda: setattr(snapshot_row, "parser_version", "changed"),
    )
    assert_database_rejects_mutation(
        db_session,
        lambda: setattr(person_row, "surname", "Changed"),
    )
    assert_database_rejects_mutation(
        db_session,
        lambda: setattr(
            person_row,
            "name_forms",
            [{"type": "reg", "surname": "Changed", "forenames": []}],
        ),
    )
    assert_database_rejects_mutation(
        db_session,
        lambda: setattr(external_id_row, "value", "changed"),
    )
    assert_database_rejects_mutation(
        db_session,
        lambda: setattr(prediction_row, "raw_label", "changed"),
    )
    assert_database_rejects_mutation(
        db_session,
        lambda: setattr(aggregated_result_row, "result_metadata", {"changed": True}),
    )
    assert_database_rejects_mutation(
        db_session,
        lambda: setattr(annotation_row, "comment", "changed"),
    )


def test_method_execution_results_project_every_snapshot_person_and_preserve_states(
    db_session: Session,
) -> None:
    repositories = session_repositories(db_session)
    project = seed_project(repositories, slug_prefix="method-results")
    people = [
        tei_person_input(tei_id="p1", surname="Unknown"),
        tei_person_input(tei_id="p2", surname="Abstained"),
        tei_person_input(tei_id="p3", surname="Errored"),
        tei_person_input(tei_id="p4", surname="Missing"),
    ]
    snapshot = seed_ready_snapshot(repositories, project.id, people)
    run = seed_run(
        repositories,
        snapshot.id,
        [MethodRunConfig(name="gender_guesser")],
    )
    now = datetime(2026, 9, 25, 12, tzinfo=UTC)
    repositories.runs.mark_run_queued(run.id)
    repositories.runs.mark_run_started(run.id, started_at=now)
    execution = repositories.runs.add_method_execution(
        MethodExecutionCreate(
            run_id=run.id,
            descriptor=MethodDescriptor(
                name="gender_guesser",
                implementation_version="gender_guesser_v1",
                normalization_version="gender_guesser_v1",
            ),
            queue_name="cpu",
            total_count=4,
        )
    )
    repositories.runs.mark_execution_queued(execution.id)
    repositories.runs.mark_execution_started(execution.id, started_at=now)
    records = repositories.projects.list_person_records_slice(snapshot.id, offset=0, limit=4)
    batches = repositories.runs.create_task_batches(
        execution.id,
        [
            TaskBatchPlan(batch_index=index, record_offset=index, record_count=1)
            for index in range(4)
        ],
    )
    expected = {
        "p1": PredictionResult(
            label=CanonicalLabel.unknown,
            status=PredictionStatus.success,
            method_confidence=0.8,
            raw_label="uncertain",
            raw_output={"source": "test"},
            metadata={"normalization": "v1"},
        ),
        "p2": PredictionResult(label=None, status=PredictionStatus.abstain, raw_label="no_name"),
        "p3": PredictionResult(label=None, status=PredictionStatus.error, raw_label="timeout"),
    }
    for batch, person in zip(batches, records, strict=True):
        claimed = repositories.runs.claim_batch(
            batch.id,
            method_execution_id=execution.id,
            worker_task_id=f"method-results-{batch.batch_index}",
            started_at=now,
            attempt_count=1,
        )
        assert claimed is not None
        result = expected.get(person.tei_id)
        if result is None:
            repositories.runs.mark_batch_finished(
                batch.id,
                status=TaskBatchStatus.failed,
                finished_at=now,
                error_count=1,
                failure_class="FixtureFailure",
                failure_diagnostic="one result could not be persisted",
            )
            continue
        repositories.runs.add_predictions(
            execution.id,
            [
                PredictionWrite(
                    person_record_id=person.id,
                    task_batch_id=batch.id,
                    input_fingerprint="f" * 64,
                    result=result,
                )
            ],
        )
        repositories.runs.mark_batch_finished(
            batch.id,
            status=TaskBatchStatus.completed,
            finished_at=now,
            success_count=int(result.status is PredictionStatus.success),
            abstain_count=int(result.status is PredictionStatus.abstain),
            error_count=int(result.status is PredictionStatus.error),
        )
    repositories.runs.finalize_execution_if_complete(execution.id, finished_at=now)
    completed_run = repositories.runs.finalize_run_if_complete(run.id, finished_at=now)
    assert completed_run.status is RunStatus.completed_with_errors

    results = repositories.runs.list_method_execution_results(
        snapshot.id,
        execution.id,
        limit=10,
    )

    assert [result.tei_id for result in results] == ["p1", "p2", "p3", "p4"]
    assert [result.result_state for result in results] == [
        MethodExecutionResultState.success,
        MethodExecutionResultState.abstain,
        MethodExecutionResultState.error,
        MethodExecutionResultState.missing,
    ]
    assert results[0].prediction is not None
    assert results[0].prediction.label is CanonicalLabel.unknown
    assert results[0].prediction.raw_label == "uncertain"
    assert set(results[0].prediction.model_dump()) == {
        "label",
        "status",
        "method_confidence",
        "raw_label",
    }
    assert results[3].prediction_id is None
    assert results[3].prediction is None
    assert [
        result.tei_id
        for result in repositories.runs.list_method_execution_results(
            snapshot.id,
            execution.id,
            limit=10,
            filters=MethodExecutionResultFilter(result_state=MethodExecutionResultState.missing),
        )
    ] == ["p4"]
    assert [
        result.tei_id
        for result in repositories.runs.list_method_execution_results(
            snapshot.id,
            execution.id,
            limit=10,
            filters=MethodExecutionResultFilter(label=CanonicalLabel.unknown),
        )
    ] == ["p1"]
    assert [
        result.tei_id
        for result in repositories.runs.list_method_execution_results(
            snapshot.id,
            execution.id,
            limit=10,
            filters=MethodExecutionResultFilter(q="errored"),
        )
    ] == ["p3"]
    continuation = repositories.runs.list_method_execution_results(
        snapshot.id,
        execution.id,
        limit=10,
        after=MethodExecutionResultCursor(
            tei_id="p2",
            person_record_id=records[1].id,
        ),
    )
    assert [result.tei_id for result in continuation] == ["p3", "p4"]
