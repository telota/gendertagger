from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from gendertagger.models.artifact import Artifact, ArtifactCreate
from gendertagger.models.classification import AgreementTier, CanonicalLabel, CertaintyTier
from gendertagger.models.review import (
    Annotation,
    AnnotationCreate,
    AnnotationHistory,
    AttributedAnnotation,
    ReviewAction,
    ReviewItemQuery,
    ReviewState,
    ReviewSummary,
    ReviewSummaryGroup,
    ReviewWorkflowState,
)
from gendertagger.models.user import CurrentUser, GlobalRole, User, UserCreate
from gendertagger.services.persistence_errors import ReviewConflictError

USER_ID = UUID("a0000000-0000-0000-0000-000000000001")
SNAPSHOT_ID = UUID("20000000-0000-0000-0000-000000000001")
PERSON_ID = UUID("40000000-0000-0000-0000-000000000001")
ANNOTATION_ID = UUID("b0000000-0000-0000-0000-000000000001")
AGGREGATED_RESULT_ID = UUID("90000000-0000-0000-0000-000000000001")
ARTIFACT_ID = UUID("30000000-0000-0000-0000-000000000001")
CREATED_AT = datetime(2026, 8, 13, 10, 0, tzinfo=UTC)


def test_provider_neutral_user_preserves_global_roles() -> None:
    command = UserCreate(
        display_name="Administrator",
        roles={GlobalRole.operator, GlobalRole.admin},
    )
    user = User(
        id=USER_ID,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
        **command.model_dump(),
    )

    assert user.roles == {GlobalRole.operator, GlobalRole.admin}
    assert user.is_active is True


def test_current_user_exposes_only_public_principal_fields() -> None:
    principal = CurrentUser(
        id=USER_ID,
        display_name="Administrator",
        roles={GlobalRole.operator, GlobalRole.admin},
    )

    assert principal.model_dump() == {
        "id": USER_ID,
        "display_name": "Administrator",
        "roles": {GlobalRole.operator, GlobalRole.admin},
    }


@pytest.mark.parametrize("project_only_role", ["viewer", "reviewer"])
def test_global_roles_exclude_project_only_roles(project_only_role: str) -> None:
    with pytest.raises(ValidationError, match="roles"):
        UserCreate.model_validate({"display_name": "Former viewer", "roles": [project_only_role]})


def test_user_rejects_blank_display_name() -> None:
    with pytest.raises(ValidationError, match="display_name must not be blank"):
        UserCreate(display_name="   ")


def test_artifact_contract_preserves_checksum_and_internal_locator() -> None:
    command = ArtifactCreate(
        logical_type="source_tei",
        storage_uri="file:///srv/gendertagger/artifacts/source.xml",
        sha256="a" * 64,
        byte_size=42,
        media_type="application/xml",
        dataset_snapshot_id=SNAPSHOT_ID,
        metadata={"profile": "reference_v1"},
    )
    artifact = Artifact(
        id=ARTIFACT_ID,
        created_at=CREATED_AT,
        **command.model_dump(),
    )

    assert artifact.sha256 == "a" * 64
    assert artifact.storage_uri.startswith("file://")
    assert artifact.metadata == {"profile": "reference_v1"}


@pytest.mark.parametrize(
    "overrides",
    [
        {"logical_type": "Source TEI"},
        {"storage_uri": "  "},
        {"sha256": "invalid"},
        {"byte_size": -1},
        {"media_type": ""},
    ],
)
def test_artifact_rejects_invalid_metadata(overrides: dict[str, object]) -> None:
    payload: dict[str, object] = {
        "logical_type": "source_tei",
        "storage_uri": "file:///source.xml",
        "sha256": "a" * 64,
        "byte_size": 42,
        "media_type": "application/xml",
    }
    payload.update(overrides)

    with pytest.raises(ValidationError):
        ArtifactCreate.model_validate(payload)


@pytest.mark.parametrize("action", [ReviewAction.verify, ReviewAction.correct])
def test_labeled_review_actions_require_canonical_label(action: ReviewAction) -> None:
    with pytest.raises(ValidationError, match="require a canonical label"):
        AnnotationCreate(
            snapshot_id=SNAPSHOT_ID,
            tei_id="p1",
            action=action,
            expected_revision=0,
        )


def test_defer_action_rejects_label() -> None:
    with pytest.raises(ValidationError, match="must not have a label"):
        AnnotationCreate(
            snapshot_id=SNAPSHOT_ID,
            tei_id="p1",
            action=ReviewAction.defer,
            label=CanonicalLabel.unknown,
            expected_revision=0,
        )


def test_annotation_command_preserves_optional_machine_result_link() -> None:
    command = AnnotationCreate(
        snapshot_id=SNAPSHOT_ID,
        tei_id="p1",
        action=ReviewAction.verify,
        label=CanonicalLabel.female,
        aggregated_result_id=AGGREGATED_RESULT_ID,
        expected_revision=0,
    )

    assert command.aggregated_result_id == AGGREGATED_RESULT_ID


def test_review_query_requires_method_name_for_method_outcome_filters() -> None:
    with pytest.raises(ValidationError, match="require method_name"):
        ReviewItemQuery(
            aggregation_id=AGGREGATED_RESULT_ID,
            method_label=CanonicalLabel.female,
        )
    with pytest.raises(ValidationError, match="q must not be blank"):
        ReviewItemQuery(aggregation_id=AGGREGATED_RESULT_ID, q="   ")


def test_review_query_orders_alternatives_by_vocabulary_and_rejects_repeats() -> None:
    query = ReviewItemQuery(
        aggregation_id=AGGREGATED_RESULT_ID,
        certainty_tiers=(CertaintyTier.contested, CertaintyTier.low),
        agreement_tiers=(AgreementTier.single_rater, AgreementTier.unanimous),
        workflow_states=(ReviewWorkflowState.deferred, ReviewWorkflowState.unreviewed),
    )

    assert query.certainty_tiers == (CertaintyTier.low, CertaintyTier.contested)
    assert query.agreement_tiers == (AgreementTier.unanimous, AgreementTier.single_rater)
    assert query.workflow_states == (
        ReviewWorkflowState.unreviewed,
        ReviewWorkflowState.deferred,
    )
    assert ReviewItemQuery(aggregation_id=AGGREGATED_RESULT_ID).certainty_tiers == ()
    with pytest.raises(ValidationError, match="must not repeat"):
        ReviewItemQuery(
            aggregation_id=AGGREGATED_RESULT_ID,
            certainty_tiers=(CertaintyTier.low, CertaintyTier.low),
        )


def _summary_group(
    certainty_tier: CertaintyTier,
    result_count: int,
) -> ReviewSummaryGroup:
    return ReviewSummaryGroup(
        certainty_tier=certainty_tier,
        agreement_tier=AgreementTier.single_rater,
        workflow_state=ReviewWorkflowState.unreviewed,
        result_count=result_count,
    )


def test_review_summary_groups_are_distinct_and_add_up() -> None:
    groups = [_summary_group(CertaintyTier.single, 2), _summary_group(CertaintyTier.uncertain, 1)]

    assert (
        ReviewSummary(aggregation_execution_id=AGGREGATED_RESULT_ID, result_count=3, groups=groups)
        .groups[0]
        .result_count
        == 2
    )
    with pytest.raises(ValidationError, match="must add up"):
        ReviewSummary(aggregation_execution_id=AGGREGATED_RESULT_ID, result_count=4, groups=groups)
    with pytest.raises(ValidationError, match="must not repeat"):
        ReviewSummary(
            aggregation_execution_id=AGGREGATED_RESULT_ID,
            result_count=4,
            groups=[groups[0], groups[0]],
        )
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        _summary_group(CertaintyTier.single, 0)


def test_review_summary_group_requires_a_review_action_exactly_when_reviewed() -> None:
    unreviewed = ReviewSummaryGroup(
        certainty_tier=CertaintyTier.high,
        agreement_tier=AgreementTier.unanimous,
        workflow_state=ReviewWorkflowState.unreviewed,
        result_count=1,
    )
    verified = ReviewSummaryGroup(
        certainty_tier=CertaintyTier.high,
        agreement_tier=AgreementTier.unanimous,
        workflow_state=ReviewWorkflowState.reviewed,
        final_label=CanonicalLabel.female,
        review_action=ReviewAction.verify,
        result_count=1,
    )
    deferred = ReviewSummaryGroup(
        certainty_tier=CertaintyTier.high,
        agreement_tier=AgreementTier.unanimous,
        workflow_state=ReviewWorkflowState.deferred,
        review_action=ReviewAction.defer,
        result_count=1,
    )

    assert unreviewed.review_action is None
    assert verified.final_label is CanonicalLabel.female
    assert deferred.review_action is ReviewAction.defer

    with pytest.raises(ValidationError, match="unreviewed group must not carry a review action"):
        ReviewSummaryGroup(
            certainty_tier=CertaintyTier.high,
            agreement_tier=AgreementTier.unanimous,
            workflow_state=ReviewWorkflowState.unreviewed,
            review_action=ReviewAction.verify,
            result_count=1,
        )
    with pytest.raises(ValidationError, match="requires a review action"):
        ReviewSummaryGroup(
            certainty_tier=CertaintyTier.high,
            agreement_tier=AgreementTier.unanimous,
            workflow_state=ReviewWorkflowState.reviewed,
            final_label=CanonicalLabel.female,
            result_count=1,
        )
    with pytest.raises(ValidationError, match="deferred group's review action must be defer"):
        ReviewSummaryGroup(
            certainty_tier=CertaintyTier.high,
            agreement_tier=AgreementTier.unanimous,
            workflow_state=ReviewWorkflowState.deferred,
            review_action=ReviewAction.verify,
            result_count=1,
        )
    with pytest.raises(
        ValidationError, match="reviewed group's review action must be verify or correct"
    ):
        ReviewSummaryGroup(
            certainty_tier=CertaintyTier.high,
            agreement_tier=AgreementTier.unanimous,
            workflow_state=ReviewWorkflowState.reviewed,
            final_label=CanonicalLabel.female,
            review_action=ReviewAction.defer,
            result_count=1,
        )
    with pytest.raises(ValidationError, match="reviewed group requires a final label"):
        ReviewSummaryGroup(
            certainty_tier=CertaintyTier.high,
            agreement_tier=AgreementTier.unanimous,
            workflow_state=ReviewWorkflowState.reviewed,
            review_action=ReviewAction.correct,
            result_count=1,
        )


def test_review_summary_groups_distinguish_by_label_and_action() -> None:
    verified = ReviewSummaryGroup(
        certainty_tier=CertaintyTier.high,
        agreement_tier=AgreementTier.unanimous,
        workflow_state=ReviewWorkflowState.reviewed,
        final_label=CanonicalLabel.female,
        review_action=ReviewAction.verify,
        result_count=2,
    )
    corrected = verified.model_copy(
        update={"review_action": ReviewAction.correct, "result_count": 1}
    )

    summary = ReviewSummary(
        aggregation_execution_id=AGGREGATED_RESULT_ID,
        result_count=3,
        last_annotated_at=CREATED_AT,
        groups=[verified, corrected],
    )

    assert summary.last_annotated_at == CREATED_AT
    with pytest.raises(ValidationError, match="must not repeat"):
        ReviewSummary(
            aggregation_execution_id=AGGREGATED_RESULT_ID,
            result_count=3,
            groups=[verified, verified.model_copy(update={"result_count": 1})],
        )


def test_annotation_preserves_append_only_revision_provenance() -> None:
    annotation = Annotation(
        id=ANNOTATION_ID,
        snapshot_id=SNAPSHOT_ID,
        person_record_id=PERSON_ID,
        tei_id="p1",
        action=ReviewAction.correct,
        label=CanonicalLabel.female,
        reviewer_user_id=USER_ID,
        comment="Checked against the source",
        aggregated_result_id=None,
        supersedes_annotation_id=None,
        resulting_revision=1,
        created_at=CREATED_AT,
    )

    assert annotation.resulting_revision == 1
    assert annotation.label is CanonicalLabel.female


def test_review_state_requires_head_after_first_revision() -> None:
    initial = ReviewState(
        snapshot_id=SNAPSHOT_ID,
        person_record_id=PERSON_ID,
        tei_id="p1",
        revision=0,
        workflow_state=ReviewWorkflowState.unreviewed,
        current_annotation_id=None,
    )
    assert initial.current_annotation_id is None

    with pytest.raises(ValidationError, match="requires a current annotation"):
        ReviewState(
            snapshot_id=SNAPSHOT_ID,
            person_record_id=PERSON_ID,
            tei_id="p1",
            revision=1,
            workflow_state=ReviewWorkflowState.reviewed,
            current_annotation_id=None,
        )


def test_review_conflict_exposes_expected_and_current_revisions() -> None:
    error = ReviewConflictError(expected_revision=1, current_revision=2)

    assert error.expected_revision == 1
    assert error.current_revision == 2
    assert str(error) == "stale review revision 1; current revision is 2"


def _attributed(revision: int, annotation_id: UUID) -> AttributedAnnotation:
    return AttributedAnnotation(
        id=annotation_id,
        snapshot_id=SNAPSHOT_ID,
        person_record_id=PERSON_ID,
        tei_id="p1",
        action=ReviewAction.verify,
        label=CanonicalLabel.female,
        reviewer_user_id=USER_ID,
        resulting_revision=revision,
        created_at=CREATED_AT,
        reviewer_display_name="Reviewer",
    )


def _history(revision: int, annotations: list[AttributedAnnotation]) -> AnnotationHistory:
    return AnnotationHistory(
        snapshot_id=SNAPSHOT_ID,
        person_record_id=PERSON_ID,
        tei_id="p1",
        revision=revision,
        workflow_state=(
            ReviewWorkflowState.reviewed if revision else ReviewWorkflowState.unreviewed
        ),
        current_annotation_id=annotations[0].id if annotations else None,
        annotations=annotations,
    )


def test_annotation_history_holds_every_revision_newest_first() -> None:
    head = _attributed(2, UUID("b0000000-0000-0000-0000-000000000002"))
    first = _attributed(1, ANNOTATION_ID)

    assert _history(0, []).annotations == []
    assert _history(2, [head, first]).current_annotation_id == head.id
    with pytest.raises(ValidationError, match="every revision"):
        _history(2, [first, head])
    with pytest.raises(ValidationError, match="every revision"):
        _history(2, [head])


def test_annotation_history_head_must_be_the_current_annotation() -> None:
    with pytest.raises(ValidationError, match="current annotation"):
        AnnotationHistory(
            **_history(1, [_attributed(1, ANNOTATION_ID)]).model_dump(
                exclude={"current_annotation_id"}
            ),
            current_annotation_id=UUID("b0000000-0000-0000-0000-000000000009"),
        )
