from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from gendertagger.api.app import create_app
from gendertagger.api.authentication import require_authenticated_user, require_csrf_protection
from gendertagger.api.dependencies import get_aggregation_service, get_project_access_service
from gendertagger.api.settings import AppSettings
from gendertagger.models.aggregation import (
    AggregatedResult,
    AggregationExecution,
    AggregationExecutionCreate,
    AggregationOutcome,
    VoteCounts,
)
from gendertagger.models.api import CursorPage
from gendertagger.models.classification import AgreementTier, CanonicalLabel, CertaintyTier
from gendertagger.models.lifecycle import AggregationExecutionStatus
from gendertagger.models.user import CurrentUser, ProjectRole
from gendertagger.services.aggregations import AggregationService
from gendertagger.services.pagination import InvalidCursorError
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.project_access_repository import ProjectScope
from gendertagger.services.unit_of_work import UnitOfWork

pytestmark = pytest.mark.unit

DATABASE_URL = "postgresql+psycopg://api:secret@localhost/gendertagger"
CODE_GIT_COMMIT = "a" * 40
DEPENDENCY_LOCK_SHA256 = "b" * 64
NOW = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)
RUN_ID = UUID("10000000-0000-0000-0000-000000000001")
METHOD_EXECUTION_ID = UUID("20000000-0000-0000-0000-000000000001")
AGGREGATION_ID = UUID("30000000-0000-0000-0000-000000000001")
RESULT_ID = UUID("40000000-0000-0000-0000-000000000001")
PERSON_ID = UUID("50000000-0000-0000-0000-000000000001")


def _unused_unit_of_work_factory() -> UnitOfWork:
    raise AssertionError("the route test must not open persistence")


class _GrantingProjectAccess:
    """Grant the caller operator in every project without persistence."""

    def effective_role(
        self, user: CurrentUser, scope: ProjectScope, resource_id: UUID
    ) -> ProjectRole:
        return ProjectRole.operator

    def has_any_grant(self, user: CurrentUser) -> bool:
        return True


def _operator() -> CurrentUser:
    return CurrentUser(
        id=UUID("60000000-0000-0000-0000-000000000001"),
        display_name="Aggregation operator",
        roles=set(),
    )


def _client(service: object) -> TestClient:
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit=CODE_GIT_COMMIT,
            dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
    )
    application.dependency_overrides[require_authenticated_user] = _operator
    application.dependency_overrides[get_project_access_service] = _GrantingProjectAccess
    application.dependency_overrides[require_csrf_protection] = lambda: None
    application.dependency_overrides[get_aggregation_service] = lambda: service
    return TestClient(application)


def _aggregation() -> AggregationExecution:
    command = AggregationExecutionCreate(
        run_id=RUN_ID,
        method_execution_ids=(METHOD_EXECUTION_ID,),
    )
    return AggregationExecution(
        id=AGGREGATION_ID,
        status=AggregationExecutionStatus.queued,
        config_sha256=command.canonical_config_sha256(),
        created_at=NOW,
        **command.model_dump(),
    )


def _result() -> AggregatedResult:
    return AggregatedResult(
        id=RESULT_ID,
        aggregation_execution_id=AGGREGATION_ID,
        person_record_id=PERSON_ID,
        outcome=AggregationOutcome.decided,
        label=CanonicalLabel.female,
        pooled_vote_counts=VoteCounts(female=1),
        agreement_score=1.0,
        agreement_tier=AgreementTier.single_rater,
        certainty_tier=CertaintyTier.uncertain,
        created_at=NOW,
    )


def test_aggregation_routes_serialize_persisted_resources() -> None:
    service = Mock(spec=AggregationService)
    aggregation = _aggregation()
    result = _result()
    service.create_aggregation.return_value = aggregation
    service.get_aggregation.return_value = aggregation
    service.list_results.return_value = CursorPage(
        items=[result],
        next_cursor=None,
        has_more=False,
    )
    service.get_result.return_value = result

    with _client(service) as client:
        created = client.post(
            f"/api/v1/runs/{RUN_ID}/aggregations",
            json={"method_execution_ids": [str(METHOD_EXECUTION_ID)]},
        )
        fetched = client.get(f"/api/v1/aggregations/{AGGREGATION_ID}")
        listed = client.get(f"/api/v1/aggregations/{AGGREGATION_ID}/results")
        result_response = client.get(f"/api/v1/aggregations/{AGGREGATION_ID}/results/{RESULT_ID}")

    assert created.status_code == 202
    assert created.json()["id"] == str(AGGREGATION_ID)
    assert service.create_aggregation.call_args.kwargs["run_id"] == RUN_ID
    assert service.create_aggregation.call_args.kwargs["command"].method_execution_ids == (
        METHOD_EXECUTION_ID,
    )
    assert fetched.json()["status"] == AggregationExecutionStatus.queued.value
    assert listed.json() == {
        "items": [result.model_dump(mode="json")],
        "next_cursor": None,
        "has_more": False,
    }
    assert result_response.json() == result.model_dump(mode="json")


def test_create_aggregation_maps_missing_and_nonaggregatable_selection() -> None:
    service = Mock(spec=AggregationService)

    with _client(service) as client:
        service.create_aggregation.side_effect = ResourceNotFoundError("missing run")
        missing = client.post(
            f"/api/v1/runs/{RUN_ID}/aggregations",
            json={"method_execution_ids": [str(METHOD_EXECUTION_ID)]},
        )
        service.create_aggregation.side_effect = InvalidResourceStateError("unfinished execution")
        conflict = client.post(
            f"/api/v1/runs/{RUN_ID}/aggregations",
            json={"method_execution_ids": [str(METHOD_EXECUTION_ID)]},
        )

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "resource_not_found"
    assert conflict.status_code == 409
    assert conflict.json()["error"] == {
        "code": "resource_conflict",
        "message": "The method execution selection is not aggregatable.",
        "details": {},
        "request_id": conflict.headers["x-request-id"],
    }


def test_aggregation_read_routes_map_missing_resources_and_invalid_cursors() -> None:
    service = Mock(spec=AggregationService)

    with _client(service) as client:
        service.get_aggregation.side_effect = ResourceNotFoundError("missing aggregation")
        missing_aggregation = client.get(f"/api/v1/aggregations/{AGGREGATION_ID}")
        service.list_results.side_effect = ResourceNotFoundError("missing aggregation")
        missing_results = client.get(f"/api/v1/aggregations/{AGGREGATION_ID}/results")
        service.list_results.side_effect = InvalidCursorError("unreadable cursor")
        invalid_cursor = client.get(
            f"/api/v1/aggregations/{AGGREGATION_ID}/results",
            params={"cursor": "unreadable"},
        )
        service.get_result.side_effect = ResourceNotFoundError("missing result")
        missing_result = client.get(f"/api/v1/aggregations/{AGGREGATION_ID}/results/{RESULT_ID}")

    for response in (missing_aggregation, missing_results, missing_result):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "resource_not_found"
    assert invalid_cursor.status_code == 422
    assert invalid_cursor.json()["error"] == {
        "code": "validation_error",
        "message": "The cursor is invalid.",
        "details": {"reason": "invalid_cursor"},
        "request_id": invalid_cursor.headers["x-request-id"],
    }
