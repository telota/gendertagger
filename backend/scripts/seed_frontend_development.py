"""Seed a representative local dataset for browser-client development.

Run this repository-only tool against a migrated development database. It deliberately uses
the same repository transitions as application services and workers, while avoiding Celery and
external classifier dependencies. Re-running it is a no-op once the marker project exists.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from functools import partial
from typing import Any
from uuid import UUID

from tests.factories import tei_person_input
from tests.seeding import (
    SEED_TIME,
    CompletedRun,
    seed_completed_aggregation,
    seed_completed_run,
    seed_pending_snapshot,
    seed_ready_snapshot,
    seed_run,
)

from gendertagger.config.run import MethodRunConfig
from gendertagger.config.settings import ArtifactStorageSettings
from gendertagger.db.session import create_database_engine, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.models.aggregation import (
    AggregationOutcome,
    AggregationResultWrite,
    ReferenceAggregationResult,
    VoteCounts,
)
from gendertagger.models.auth import validate_local_password_length
from gendertagger.models.classification import (
    AgreementTier,
    CanonicalLabel,
    CertaintyTier,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.evaluation import (
    EvaluationDefinition,
    EvaluationExecutionCreate,
    EvaluationTaskMessage,
)
from gendertagger.models.export import (
    ExportExecutionCreate,
    ExportFormat,
    ExportTaskMessage,
    LabelSourcePolicy,
)
from gendertagger.models.lifecycle import MethodExecutionStatus, RunStatus
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.project import ProjectCreate
from gendertagger.models.team import TeamCreate
from gendertagger.models.review import AnnotationCreate, ReviewAction
from gendertagger.models.run import MethodExecutionCreate
from gendertagger.models.user import GlobalRole, ProjectRole, UserCreate
from gendertagger.services.evaluation_execution import EvaluationExecutor
from gendertagger.services.export_execution import ExportExecutor
from gendertagger.services.password_hashing import Argon2PasswordHasher
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from gendertagger.storage.local import LocalArtifactStorage

MARKER_PROJECT_SLUG = "frontend-demo"
SECONDARY_PROJECT_SLUG = "frontend-demo-lifecycle"
DEFAULT_PASSWORD = "development-only"  # noqa: S105 - documented disposable local credential.
MAX_GENERATED_ARTIFACT_BYTES = 10 * 1024 * 1024
_ERROR_PERSON_INDEX = 7
_ERROR_RESULT_POSITION = 6
_METHODS = (*REFERENCE_REQUIRED_METHODS, "hivoto_xgboost")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-development-database",
        action="store_true",
        help="Required acknowledgement that the configured database is disposable development data.",
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help="Shared local password for the three demo accounts (default: development-only).",
    )
    return parser


def _prediction(method_name: str, person: Any) -> PredictionResult:
    """Return deterministic synthetic evidence with success, abstain, and error examples."""
    index = int(person.tei_id.rsplit("-", maxsplit=1)[-1])
    if method_name == "parenthetical_qualifier":
        return PredictionResult(label=None, status=PredictionStatus.abstain)
    if method_name == "hivoto_xgboost" and index == _ERROR_PERSON_INDEX:
        return PredictionResult(
            label=None,
            status=PredictionStatus.error,
            raw_output={
                "error_code": "synthetic_failure",
                "error_message": "Synthetic per-record classifier failure.",
            },
        )
    if method_name != "gnd" and (index + len(method_name)) % 5 == 0:
        return PredictionResult(label=None, status=PredictionStatus.abstain)
    label = CanonicalLabel.male if index % 2 else CanonicalLabel.female
    if method_name in {"wiki_gendersort", "hf_genderize"} and index in {3, 4}:
        label = CanonicalLabel.female if label is CanonicalLabel.male else CanonicalLabel.male
    metadata = {"self_reported_certainty": "high"} if method_name == "local_llm" else {}
    return PredictionResult(
        label=label,
        status=PredictionStatus.success,
        raw_label=label.value,
        method_confidence=0.8,
        metadata=metadata,
    )


def _tier_results(completed: CompletedRun) -> list[AggregationResultWrite]:
    people = [completed.people[f"demo-{index}"] for index in range(1, 8)]
    results = [
        ReferenceAggregationResult(
            outcome=AggregationOutcome.decided,
            label=CanonicalLabel.male,
            pooled_vote_counts=VoteCounts(male=4),
            agreement_score=1.0,
            agreement_tier=AgreementTier.unanimous,
            certainty_tier=CertaintyTier.high,
        ),
        ReferenceAggregationResult(
            outcome=AggregationOutcome.decided,
            label=CanonicalLabel.female,
            pooled_vote_counts=VoteCounts(female=3, male=1),
            agreement_score=0.75,
            agreement_tier=AgreementTier.strong_majority,
            certainty_tier=CertaintyTier.high,
        ),
        ReferenceAggregationResult(
            outcome=AggregationOutcome.decided,
            label=CanonicalLabel.male,
            pooled_vote_counts=VoteCounts(male=2, female=1, unknown=1),
            agreement_score=0.5,
            agreement_tier=AgreementTier.weak_majority,
            certainty_tier=CertaintyTier.low,
        ),
        ReferenceAggregationResult(
            outcome=AggregationOutcome.unresolved_tie,
            label=None,
            pooled_vote_counts=VoteCounts(male=2, female=2),
            tied_labels=(CanonicalLabel.male, CanonicalLabel.female),
            agreement_score=0.5,
            agreement_tier=AgreementTier.no_consensus,
            certainty_tier=CertaintyTier.contested,
        ),
        ReferenceAggregationResult(
            outcome=AggregationOutcome.decided,
            label=CanonicalLabel.institution,
            pooled_vote_counts=VoteCounts(institution=1),
            agreement_score=1.0,
            agreement_tier=AgreementTier.single_rater,
            certainty_tier=CertaintyTier.single,
        ),
        ReferenceAggregationResult(
            outcome=AggregationOutcome.decided,
            label=CanonicalLabel.unknown,
            pooled_vote_counts=VoteCounts(unknown=1),
            agreement_score=1.0,
            agreement_tier=AgreementTier.single_rater,
            certainty_tier=CertaintyTier.uncertain,
        ),
        ReferenceAggregationResult(
            outcome=AggregationOutcome.no_data,
            label=None,
            agreement_score=None,
            agreement_tier=AgreementTier.no_answer,
            certainty_tier=CertaintyTier.no_data,
        ),
    ]
    return [
        AggregationResultWrite(
            person_record_id=person.id,
            result=result,
            has_prediction_error=position == _ERROR_RESULT_POSITION,
            metadata={"fixture": "frontend_development_v1"},
        )
        for position, (person, result) in enumerate(zip(people, results, strict=True))
    ]


def _add_account(
    unit_of_work: UnitOfWork,
    *,
    username: str,
    display_name: str,
    password_hash: str,
    global_roles: set[GlobalRole] | None = None,
) -> Any:
    user = unit_of_work.users.add_user(
        UserCreate(display_name=display_name, roles=global_roles or set())
    )
    unit_of_work.auth.add_credential(
        user_id=user.id,
        username=username,
        password_hash=password_hash,
    )
    unit_of_work.auth.set_password(
        user_id=user.id,
        password_hash=password_hash,
        must_change_password=False,
    )
    return user


def _seed_database(unit_of_work_factory: UnitOfWorkFactory, password: str) -> dict[str, Any]:
    with unit_of_work_factory() as unit_of_work:
        existing = unit_of_work.projects.get_project_by_slug(MARKER_PROJECT_SLUG)
        if existing is not None:
            return {"status": "already_seeded", "project_id": str(existing.id)}

        password_hash = Argon2PasswordHasher().hash(password)
        viewer = _add_account(
            unit_of_work,
            username="frontend-viewer",
            display_name="Frontend Viewer",
            password_hash=password_hash,
        )
        reviewer = _add_account(
            unit_of_work,
            username="frontend-reviewer",
            display_name="Frontend Reviewer",
            password_hash=password_hash,
        )
        operator = _add_account(
            unit_of_work,
            username="frontend-operator",
            display_name="Frontend Operator",
            password_hash=password_hash,
            global_roles={GlobalRole.operator},
        )
        team = unit_of_work.teams.add_team(
            TeamCreate(slug="frontend-demonstration", display_name="Frontend demonstration team")
        )
        for user in (viewer, reviewer, operator):
            unit_of_work.teams.add_member(team.id, user.id)

        project = unit_of_work.projects.add_project(
            ProjectCreate(
                slug=MARKER_PROJECT_SLUG,
                display_name="Frontend demonstration",
                description="Representative data for browser-client development.",
                team_id=team.id,
                initial_manager_user_id=operator.id,
            ),
            manager_user_id=operator.id,
            created_by_user_id=operator.id,
        )
        lifecycle_project = unit_of_work.projects.add_project(
            ProjectCreate(
                slug=SECONDARY_PROJECT_SLUG,
                display_name="Frontend lifecycle states",
                description="Failed and in-progress resources for browser-client development.",
                team_id=team.id,
                initial_manager_user_id=operator.id,
            ),
            manager_user_id=operator.id,
            created_by_user_id=operator.id,
        )
        for project_id in (project.id, lifecycle_project.id):
            unit_of_work.access.set_member_role(project_id, viewer.id, ProjectRole.viewer)
            unit_of_work.access.set_member_role(project_id, reviewer.id, ProjectRole.reviewer)
            unit_of_work.access.set_member_role(project_id, operator.id, ProjectRole.operator)

        people = [
            tei_person_input(
                tei_id=f"demo-{index}",
                surname=surname,
                forenames=[forename],
                gnd_id=f"10{index:02d}-demo",
                note=f"Synthetic frontend fixture covering tier case {index}.",
            )
            for index, (surname, forename) in enumerate(
                (
                    ("Müller", "Ada"),
                    ("Schmidt", "Béla"),
                    ("Nguyen", "Chi"),
                    ("Okafor", "Dayo"),
                    ("Archiv", "Historisches"),
                    ("Rossi", "Elena"),
                    ("Unbekannt", "Fall"),
                ),
                start=1,
            )
        ]
        ready_snapshot = seed_ready_snapshot(unit_of_work, project.id, people)
        failed_snapshot = seed_pending_snapshot(unit_of_work, lifecycle_project.id)
        claimed = unit_of_work.projects.claim_snapshot_import(failed_snapshot.id)
        if claimed is None:
            msg = "new synthetic snapshot could not be claimed"
            raise RuntimeError(msg)
        failed_snapshot = unit_of_work.projects.fail_snapshot_import(
            failed_snapshot.id,
            failure_diagnostic="Synthetic malformed source for frontend error-state testing.",
        )

        completed = seed_completed_run(unit_of_work, ready_snapshot, _METHODS, _prediction)
        execution_by_name: dict[str, UUID] = dict(
            zip(_METHODS, completed.execution_ids, strict=True)
        )
        aggregation = seed_completed_aggregation(
            unit_of_work,
            completed.run.id,
            [execution_by_name[name] for name in REFERENCE_REQUIRED_METHODS],
            results=_tier_results(completed),
        )
        unit_of_work.projects.set_working_aggregation(
            project.id,
            aggregation_execution_id=aggregation.id,
        )

        aggregated_results = {
            result.person_record_id: result
            for result in unit_of_work.aggregations.list_results(aggregation.id, limit=100)
        }
        first = completed.people["demo-1"]
        first_result = aggregated_results[first.id]
        unit_of_work.reviews.add_annotation(
            AnnotationCreate(
                snapshot_id=ready_snapshot.id,
                tei_id=first.tei_id,
                action=ReviewAction.verify,
                label=CanonicalLabel.male,
                comment="Initial synthetic verification.",
                aggregated_result_id=first_result.id,
                expected_revision=0,
            ),
            reviewer_user_id=reviewer.id,
        )
        unit_of_work.reviews.add_annotation(
            AnnotationCreate(
                snapshot_id=ready_snapshot.id,
                tei_id=first.tei_id,
                action=ReviewAction.correct,
                label=CanonicalLabel.female,
                comment="Second revision for annotation-history testing.",
                aggregated_result_id=first_result.id,
                expected_revision=1,
            ),
            reviewer_user_id=reviewer.id,
        )
        second = completed.people["demo-2"]
        unit_of_work.reviews.add_annotation(
            AnnotationCreate(
                snapshot_id=ready_snapshot.id,
                tei_id=second.tei_id,
                action=ReviewAction.defer,
                comment="Deferred synthetic review case.",
                aggregated_result_id=aggregated_results[second.id].id,
                expected_revision=0,
            ),
            reviewer_user_id=reviewer.id,
        )

        running_run = seed_run(
            unit_of_work,
            ready_snapshot.id,
            [MethodRunConfig(name="gender_guesser")],
        )
        unit_of_work.runs.mark_run_queued(running_run.id)
        running_run = unit_of_work.runs.mark_run_started(running_run.id, started_at=SEED_TIME)

        failed_run = seed_run(
            unit_of_work,
            ready_snapshot.id,
            [MethodRunConfig(name="gender_guesser")],
        )
        unit_of_work.runs.mark_run_queued(failed_run.id)
        unit_of_work.runs.mark_run_started(failed_run.id, started_at=SEED_TIME)
        failed_execution = unit_of_work.runs.add_method_execution(
            MethodExecutionCreate(
                run_id=failed_run.id,
                descriptor=MethodDescriptor(
                    name="gender_guesser",
                    implementation_version="synthetic_v1",
                    normalization_version="synthetic_v1",
                ),
                queue_name="cpu",
                total_count=len(people),
            )
        )
        unit_of_work.runs.mark_execution_queued(failed_execution.id)
        unit_of_work.runs.mark_execution_started(failed_execution.id, started_at=SEED_TIME)
        failed_execution = unit_of_work.runs.mark_execution_finished(
            failed_execution.id,
            status=MethodExecutionStatus.failed,
            finished_at=SEED_TIME,
            failure_class="SyntheticMethodFailure",
            failure_diagnostic="Synthetic execution failure for frontend error-state testing.",
        )
        failed_run = unit_of_work.runs.mark_run_finished(
            failed_run.id,
            status=RunStatus.failed,
            finished_at=SEED_TIME,
            failure_diagnostic="Synthetic run failure for frontend error-state testing.",
        )

        definition = EvaluationDefinition()
        evaluation = unit_of_work.evaluations.add_evaluation(
            EvaluationExecutionCreate(
                run_id=completed.run.id,
                definition=definition.id,
                resolved_config=definition.model_dump(mode="json"),
                method_execution_ids=tuple(
                    execution_by_name[name] for name in definition.required_methods
                ),
                aggregation_execution_id=aggregation.id,
            )
        )
        export = unit_of_work.exports.add_export(
            ExportExecutionCreate(
                run_id=completed.run.id,
                aggregation_execution_id=aggregation.id,
                format=ExportFormat.json,
                label_source_policy=LabelSourcePolicy.human_overrides,
            )
        )
        unit_of_work.commit()

    return {
        "status": "created",
        "accounts": {
            "viewer": {"username": "frontend-viewer", "user_id": str(viewer.id)},
            "reviewer": {"username": "frontend-reviewer", "user_id": str(reviewer.id)},
            "operator": {"username": "frontend-operator", "user_id": str(operator.id)},
        },
        "project_id": str(project.id),
        "lifecycle_project_id": str(lifecycle_project.id),
        "ready_snapshot_id": str(ready_snapshot.id),
        "failed_snapshot_id": str(failed_snapshot.id),
        "completed_run_id": str(completed.run.id),
        "running_run_id": str(running_run.id),
        "failed_run_id": str(failed_run.id),
        "failed_method_execution_id": str(failed_execution.id),
        "aggregation_id": str(aggregation.id),
        "evaluation_id": str(evaluation.id),
        "export_id": str(export.id),
        "annotation_conflict_example": {
            "snapshot_id": str(ready_snapshot.id),
            "tei_id": first.tei_id,
            "stale_expected_revision": 1,
            "current_revision": 2,
        },
    }


def seed_frontend_development(
    *, password: str, settings: ArtifactStorageSettings
) -> dict[str, Any]:
    """Create the fixture graph and finish its asynchronous evaluation and export."""
    validate_local_password_length(password)
    engine = create_database_engine(settings.database_url.get_secret_value())
    session_factory = create_session_factory(engine)
    unit_of_work_factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    try:
        result = _seed_database(unit_of_work_factory, password)
        if result["status"] == "already_seeded":
            return result
        storage = LocalArtifactStorage(settings.artifact_root)
        clock = partial(datetime.now, UTC)
        evaluation = EvaluationExecutor(
            unit_of_work_factory=unit_of_work_factory,
            artifact_storage=storage,
            max_report_bytes=MAX_GENERATED_ARTIFACT_BYTES,
            clock=clock,
        ).execute(
            EvaluationTaskMessage(evaluation_execution_id=result["evaluation_id"]),
            attempt_count=1,
        )
        export = ExportExecutor(
            unit_of_work_factory=unit_of_work_factory,
            artifact_storage=storage,
            max_output_bytes=MAX_GENERATED_ARTIFACT_BYTES,
            clock=clock,
        ).execute(
            ExportTaskMessage(export_execution_id=result["export_id"]),
            attempt_count=1,
        )
        result["evaluation_status"] = evaluation.status.value
        result["export_status"] = export.status.value
        return result
    finally:
        engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the safety acknowledgement, seed the configured database, and print JSON."""
    args = _parser().parse_args(argv)
    if not args.confirm_development_database:
        _parser().error("--confirm-development-database is required")
    settings = ArtifactStorageSettings()  # type: ignore[call-arg]
    result = seed_frontend_development(password=str(args.password), settings=settings)
    if result["status"] == "created":
        result["password"] = str(args.password)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
