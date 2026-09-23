from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from tests.factories import tei_person_input
from tests.seeding import (
    seed_completed_aggregation,
    seed_completed_run,
    seed_member,
    seed_project,
    seed_ready_snapshot,
)

from gendertagger.api.app import create_app
from gendertagger.api.authentication import AuthenticationBackend
from gendertagger.api.settings import AppSettings
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.models.aggregation import (
    AggregationExecutionCreate,
    AggregationOutcome,
    AggregationResultWrite,
    OverrideSource,
    ReferenceAggregationResult,
    VoteCounts,
)
from gendertagger.models.classification import (
    AgreementTier,
    CanonicalLabel,
    CertaintyTier,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.person import PersonRecord
from gendertagger.models.review import (
    AnnotationCreate,
    ReviewAction,
    ReviewItemSort,
    ReviewWorkflowState,
)
from gendertagger.services.unit_of_work import UnitOfWork, UnitOfWorkFactory

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

DATABASE_URL = "postgresql+psycopg://unused:unused@localhost/unused"
CODE_GIT_COMMIT = "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b"
DEPENDENCY_LOCK_SHA256 = "b" * 64
NOW = datetime(2026, 8, 14, 18, 0, tzinfo=UTC)


class StaticAuthenticationBackend(AuthenticationBackend):
    def __init__(self, user_id: UUID) -> None:
        self._user_id = user_id

    def authenticate(self, request: Request) -> UUID | None:
        return self._user_id

    def validate_csrf(self, request: Request, *, user_id: UUID) -> bool:
        return user_id == self._user_id


def _unit_of_work_factory(
    engine: Engine,
) -> tuple[UnitOfWorkFactory, sessionmaker[Session]]:
    session_factory = create_session_factory(engine)

    def factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return factory, session_factory


def _seed_review_items(
    unit_of_work_factory: UnitOfWorkFactory,
    _session_factory: sessionmaker[Session],
) -> tuple[UUID, UUID]:
    with unit_of_work_factory() as unit_of_work:
        project = seed_project(unit_of_work, slug_prefix="review-query")
        reviewer = seed_member(unit_of_work, project.id, display_name="Review query operator")
        snapshot = seed_ready_snapshot(
            unit_of_work,
            project.id,
            [
                tei_person_input(
                    tei_id="p3", surname="Third", external_ids={"wikidata": "QSearch"}
                ),
                tei_person_input(tei_id="p1", surname="First"),
                tei_person_input(tei_id="p2", surname="Second"),
                tei_person_input(tei_id="p4", surname="Fourth"),
            ],
        )
        completed = seed_completed_run(
            unit_of_work, snapshot, REFERENCE_REQUIRED_METHODS, _gender_guesser_varies
        )
        unit_of_work.commit()
    person_one, person_two, person_three, person_four = (
        completed.people[tei_id] for tei_id in ("p1", "p2", "p3", "p4")
    )

    with unit_of_work_factory() as unit_of_work:
        aggregation = seed_completed_aggregation(
            unit_of_work,
            completed.run.id,
            completed.execution_ids,
            results=[
                AggregationResultWrite(
                    person_record_id=person_one.id,
                    result=ReferenceAggregationResult(
                        outcome=AggregationOutcome.unresolved_tie,
                        label=None,
                        pooled_vote_counts=VoteCounts(male=1, female=1),
                        tied_labels=(CanonicalLabel.male, CanonicalLabel.female),
                        agreement_score=0.5,
                        agreement_tier=AgreementTier.no_consensus,
                        certainty_tier=CertaintyTier.contested,
                    ),
                    has_prediction_error=True,
                ),
                AggregationResultWrite(
                    person_record_id=person_two.id,
                    result=ReferenceAggregationResult(
                        outcome=AggregationOutcome.decided,
                        label=CanonicalLabel.male,
                        pooled_vote_counts=VoteCounts(male=1),
                        agreement_score=1.0,
                        agreement_tier=AgreementTier.single_rater,
                        certainty_tier=CertaintyTier.uncertain,
                    ),
                ),
                AggregationResultWrite(
                    person_record_id=person_three.id,
                    result=ReferenceAggregationResult(
                        outcome=AggregationOutcome.decided,
                        label=CanonicalLabel.female,
                        pooled_vote_counts=VoteCounts(male=1, female=1),
                        override_source=OverrideSource.gnd,
                        override_agreeing_count=1,
                        override_comparison_count=2,
                        agreement_score=0.5,
                        agreement_tier=AgreementTier.weak_majority,
                        certainty_tier=CertaintyTier.high,
                    ),
                ),
                AggregationResultWrite(
                    person_record_id=person_four.id,
                    result=ReferenceAggregationResult(
                        outcome=AggregationOutcome.decided,
                        label=CanonicalLabel.male,
                        pooled_vote_counts=VoteCounts(male=1),
                        agreement_score=1.0,
                        agreement_tier=AgreementTier.single_rater,
                        certainty_tier=CertaintyTier.single,
                    ),
                ),
            ],
        )
        persisted_results = unit_of_work.aggregations.list_results(aggregation.id, limit=10)
        results_by_person = {result.person_record_id: result for result in persisted_results}
        unit_of_work.reviews.add_annotation(
            AnnotationCreate(
                snapshot_id=snapshot.id,
                tei_id="p2",
                action=ReviewAction.correct,
                label=CanonicalLabel.female,
                aggregated_result_id=results_by_person[person_two.id].id,
                expected_revision=0,
            ),
            reviewer_user_id=reviewer.id,
        )
        unit_of_work.reviews.add_annotation(
            AnnotationCreate(
                snapshot_id=snapshot.id,
                tei_id="p3",
                action=ReviewAction.defer,
                aggregated_result_id=results_by_person[person_three.id].id,
                expected_revision=0,
            ),
            reviewer_user_id=reviewer.id,
        )
        unit_of_work.commit()
    return reviewer.id, aggregation.id


def _gender_guesser_varies(method_name: str, person: PersonRecord) -> PredictionResult:
    """gender_guesser errs on p1, says male for p2 and female for p3; everything else abstains."""
    if method_name == "gender_guesser" and person.tei_id == "p1":
        return PredictionResult(
            label=None,
            status=PredictionStatus.error,
            raw_label="error",
            raw_output={"diagnostic": "synthetic"},
        )
    labels = {"p2": CanonicalLabel.male, "p3": CanonicalLabel.female}
    if method_name == "gender_guesser" and person.tei_id in labels:
        label = labels[person.tei_id]
        return PredictionResult(label=label, status=PredictionStatus.success, raw_label=label.value)
    return PredictionResult(label=None, status=PredictionStatus.abstain)


def _client(postgres_engine: Engine, artifact_root: Path) -> tuple[TestClient, UUID]:
    unit_of_work_factory, session_factory = _unit_of_work_factory(postgres_engine)
    reviewer_id, aggregation_id = _seed_review_items(
        unit_of_work_factory,
        session_factory,
    )
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit=CODE_GIT_COMMIT,
            dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
            artifact_root=artifact_root,
        ),
        unit_of_work_factory=unit_of_work_factory,
        authentication_backend=StaticAuthenticationBackend(reviewer_id),
    )
    return TestClient(application), aggregation_id


def _tei_ids(response: object) -> list[str]:
    assert isinstance(response, dict)
    items = response["items"]
    assert isinstance(items, list)
    return [str(item["tei_id"]) for item in items]


def test_review_items_project_final_state_and_paginate_stably(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, aggregation_id = _client(postgres_engine, tmp_path)
    register_order: dict[str, str | int] = {
        "aggregation_id": str(aggregation_id),
        "sort": ReviewItemSort.tei_id.value,
        "limit": 2,
    }
    first_page = client.get("/api/v1/review-items", params=register_order).json()
    second_page = client.get(
        "/api/v1/review-items",
        params={**register_order, "cursor": first_page["next_cursor"]},
    ).json()

    assert _tei_ids(first_page) == ["p1", "p2"]
    assert _tei_ids(second_page) == ["p3", "p4"]
    first_item, second_item = first_page["items"]
    third_item = second_page["items"][0]
    assert first_item["final_label"] is None
    assert first_item["workflow_state"] == ReviewWorkflowState.unreviewed.value
    assert first_item["has_prediction_error"] is True
    assert second_item["machine_label"] == CanonicalLabel.male.value
    assert second_item["final_label"] == CanonicalLabel.female.value
    assert second_item["workflow_state"] == ReviewWorkflowState.reviewed.value
    assert third_item["has_authority_conflict"] is True
    assert third_item["workflow_state"] == ReviewWorkflowState.deferred.value
    assert third_item["final_label"] == CanonicalLabel.female.value


def test_review_items_default_to_server_side_uncertainty_first_ordering(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, aggregation_id = _client(postgres_engine, tmp_path)
    triage_page = client.get(
        "/api/v1/review-items",
        params={"aggregation_id": str(aggregation_id)},
    ).json()
    register_page = client.get(
        "/api/v1/review-items",
        params={
            "aggregation_id": str(aggregation_id),
            "sort": ReviewItemSort.tei_id.value,
        },
    ).json()

    assert _tei_ids(triage_page) == ["p1", "p2", "p4", "p3"]
    assert _tei_ids(register_page) == ["p1", "p2", "p3", "p4"]
    assert [item["certainty_tier"] for item in triage_page["items"]] == [
        CertaintyTier.contested.value,
        CertaintyTier.uncertain.value,
        CertaintyTier.single.value,
        CertaintyTier.high.value,
    ]
    assert triage_page["items"][3]["has_authority_conflict"] is True


def test_uncertainty_pages_are_stable_and_scoped_to_their_sort(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    """Annotating a later page must not move it: review state is not a sort key."""
    client, aggregation_id = _client(postgres_engine, tmp_path)
    triage_order: dict[str, str | int] = {"aggregation_id": str(aggregation_id), "limit": 2}
    first_page = client.get("/api/v1/review-items", params=triage_order).json()
    assert _tei_ids(first_page) == ["p1", "p2"]

    annotation = client.post(
        "/api/v1/annotations",
        json={
            "snapshot_id": first_page["items"][0]["snapshot_id"],
            "tei_id": "p4",
            "action": ReviewAction.verify.value,
            "label": CanonicalLabel.male.value,
            "expected_revision": 0,
        },
    )
    assert annotation.status_code == 201

    second_page = client.get(
        "/api/v1/review-items",
        params={**triage_order, "cursor": first_page["next_cursor"]},
    ).json()
    cross_sort_response = client.get(
        "/api/v1/review-items",
        params={
            **triage_order,
            "sort": ReviewItemSort.tei_id.value,
            "cursor": first_page["next_cursor"],
        },
    )

    assert _tei_ids(second_page) == ["p4", "p3"]
    assert second_page["items"][0]["workflow_state"] == ReviewWorkflowState.reviewed.value
    assert second_page["has_more"] is False
    assert cross_sort_response.status_code == 422
    assert cross_sort_response.json()["error"]["details"] == {"reason": "invalid_cursor"}


def test_review_item_filters_are_server_side_and_composable(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, aggregation_id = _client(postgres_engine, tmp_path)
    base = {"aggregation_id": str(aggregation_id)}
    cases = [
        ({"certainty_tiers": CertaintyTier.contested.value}, ["p1"]),
        ({"agreement_tiers": AgreementTier.weak_majority.value}, ["p3"]),
        ({"final_label": CanonicalLabel.female.value}, ["p2", "p3"]),
        ({"workflow_states": ReviewWorkflowState.reviewed.value}, ["p2"]),
        ({"has_authority_conflict": "true"}, ["p3"]),
        ({"has_prediction_error": "true"}, ["p1"]),
        ({"method_name": "gender_guesser", "prediction_status": "error"}, ["p1"]),
        ({"method_name": "gender_guesser", "method_label": "male"}, ["p2"]),
        ({"q": "Second"}, ["p2"]),
        ({"q": "QSearch"}, ["p3"]),
    ]

    for filters, expected_tei_ids in cases:
        response = client.get(
            "/api/v1/review-items",
            params={**base, **filters},
        )
        assert response.status_code == 200
        assert _tei_ids(response.json()) == expected_tei_ids

    method_response = client.get(
        "/api/v1/review-items",
        params={**base, "method_name": "gender_guesser", "method_label": "male"},
    ).json()
    assert method_response["items"][0]["selected_method_result"] == {
        "method_name": "gender_guesser",
        "status": PredictionStatus.success.value,
        "label": CanonicalLabel.male.value,
    }


def test_review_cursor_is_filter_scoped_and_method_filters_require_name(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, aggregation_id = _client(postgres_engine, tmp_path)
    first_page = client.get(
        "/api/v1/review-items",
        params={
            "aggregation_id": str(aggregation_id),
            "final_label": CanonicalLabel.female.value,
            "limit": 1,
        },
    ).json()

    cross_filter_response = client.get(
        "/api/v1/review-items",
        params={
            "aggregation_id": str(aggregation_id),
            "limit": 1,
            "cursor": first_page["next_cursor"],
        },
    )
    missing_method_response = client.get(
        "/api/v1/review-items",
        params={
            "aggregation_id": str(aggregation_id),
            "method_label": CanonicalLabel.male.value,
        },
    )

    assert cross_filter_response.status_code == 422
    assert cross_filter_response.json()["error"]["details"] == {"reason": "invalid_cursor"}
    assert missing_method_response.status_code == 422
    assert missing_method_response.json()["error"]["code"] == "validation_error"


def test_review_queue_matches_any_listed_tier_or_state(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, aggregation_id = _client(postgres_engine, tmp_path)
    base = {"aggregation_id": str(aggregation_id), "sort": "tei_id"}
    contested_evidence = ["low", "contested"]
    thin_evidence = ["single", "uncertain"]
    cases: list[tuple[dict[str, str | list[str]], list[str]]] = [
        ({"certainty_tiers": contested_evidence, "workflow_states": "unreviewed"}, ["p1"]),
        ({"certainty_tiers": thin_evidence}, ["p2", "p4"]),
        ({"certainty_tiers": thin_evidence, "workflow_states": "unreviewed"}, ["p4"]),
        ({"workflow_states": ["unreviewed", "deferred"]}, ["p1", "p3", "p4"]),
        ({"agreement_tiers": ["single_rater", "no_consensus"]}, ["p1", "p2", "p4"]),
    ]

    for filters, expected_tei_ids in cases:
        response = client.get("/api/v1/review-items", params={**base, **filters})
        assert response.status_code == 200
        assert _tei_ids(response.json()) == expected_tei_ids

    first_page = client.get(
        "/api/v1/review-items",
        params={**base, "certainty_tiers": thin_evidence, "limit": 1},
    ).json()
    reordered = client.get(
        "/api/v1/review-items",
        params={
            **base,
            "certainty_tiers": list(reversed(thin_evidence)),
            "limit": 1,
            "cursor": first_page["next_cursor"],
        },
    )
    repeated = client.get(
        "/api/v1/review-items",
        params={**base, "certainty_tiers": ["low", "low"]},
    )

    assert _tei_ids(first_page) == ["p2"]
    assert reordered.status_code == 200
    assert _tei_ids(reordered.json()) == ["p4"]
    assert repeated.status_code == 422
    assert repeated.json()["error"]["code"] == "validation_error"


def test_review_summary_counts_what_the_review_queue_returns(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    unit_of_work_factory, session_factory = _unit_of_work_factory(postgres_engine)
    reviewer_id, aggregation_id = _seed_review_items(unit_of_work_factory, session_factory)
    client = TestClient(
        create_app(
            settings=AppSettings(
                database_url=SecretStr(DATABASE_URL),
                code_git_commit=CODE_GIT_COMMIT,
                dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
                artifact_root=tmp_path,
            ),
            unit_of_work_factory=unit_of_work_factory,
            authentication_backend=StaticAuthenticationBackend(reviewer_id),
        )
    )

    summary = client.get(f"/api/v1/aggregations/{aggregation_id}/review-summary")
    summary_body = summary.json()

    assert summary.status_code == 200
    last_annotated_at = summary_body.pop("last_annotated_at")
    assert last_annotated_at is not None
    assert datetime.fromisoformat(last_annotated_at) > NOW
    assert summary_body == {
        "aggregation_execution_id": str(aggregation_id),
        "result_count": 4,
        "groups": [
            {
                "certainty_tier": "high",
                "agreement_tier": "weak_majority",
                "workflow_state": "deferred",
                # p3 deferred: defer never overrides, so the machine's own gnd-backed label stands.
                "final_label": "female",
                "review_action": "defer",
                "result_count": 1,
            },
            {
                "certainty_tier": "contested",
                "agreement_tier": "no_consensus",
                "workflow_state": "unreviewed",
                # p1's unresolved tie has no machine label and nobody has annotated it.
                "final_label": None,
                "review_action": None,
                "result_count": 1,
            },
            {
                "certainty_tier": "single",
                "agreement_tier": "single_rater",
                "workflow_state": "unreviewed",
                # p4 unreviewed: the machine's own label is still the final decision.
                "final_label": "male",
                "review_action": None,
                "result_count": 1,
            },
            {
                "certainty_tier": "uncertain",
                "agreement_tier": "single_rater",
                "workflow_state": "reviewed",
                # p2 corrected: the human label supersedes the machine's "male".
                "final_label": "female",
                "review_action": "correct",
                "result_count": 1,
            },
        ],
    }
    thin_unreviewed_count = sum(
        group["result_count"]
        for group in summary.json()["groups"]
        if group["certainty_tier"] in {"single", "uncertain"}
        and group["workflow_state"] == "unreviewed"
    )
    thin_unreviewed_queue = client.get(
        "/api/v1/review-items",
        params={
            "aggregation_id": str(aggregation_id),
            "certainty_tiers": ["single", "uncertain"],
            "workflow_states": "unreviewed",
        },
    ).json()
    assert thin_unreviewed_count == len(thin_unreviewed_queue["items"]) == 1

    with unit_of_work_factory() as unit_of_work:
        completed = unit_of_work.aggregations.get_aggregation(aggregation_id)
        assert completed is not None
        pending = unit_of_work.aggregations.add_aggregation(
            AggregationExecutionCreate(
                run_id=completed.run_id,
                method_execution_ids=tuple(reversed(completed.method_execution_ids)),
            )
        )
        unit_of_work.commit()
    not_ready = client.get(f"/api/v1/aggregations/{pending.id}/review-summary")
    missing = client.get(f"/api/v1/aggregations/{uuid4()}/review-summary")

    assert not_ready.status_code == 409
    assert not_ready.json()["error"]["code"] == "resource_conflict"
    assert missing.status_code == 404
