from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine

from gendertagger.api.app import create_app
from gendertagger.api.authentication import (
    AuthenticationBackend,
    require_authenticated_user,
    require_csrf_protection,
)
from gendertagger.api.settings import AppSettings
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.ingestion.tei import TeiPersonParser
from gendertagger.models.classification import CanonicalLabel
from gendertagger.models.project import SnapshotImportTaskMessage
from gendertagger.models.review import ReviewAction, ReviewWorkflowState
from gendertagger.models.team import TeamCreate
from gendertagger.models.user import CurrentUser, GlobalRole, ProjectRole, UserCreate
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from gendertagger.services.snapshot_import import SnapshotImportExecutor
from gendertagger.storage.local import LocalArtifactStorage

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

DATABASE_URL = "postgresql+psycopg://unused:unused@localhost/unused"
CODE_GIT_COMMIT = "c" * 40
DEPENDENCY_LOCK_SHA256 = "d" * 64
VALID_TEI = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0">
<text><body><listPerson><person xml:id="p1"><persName type="reg"><surname>Example</surname></persName></person></listPerson></body></text>
</TEI>"""


class StaticAuthenticationBackend(AuthenticationBackend):
    def __init__(self, user_id: UUID) -> None:
        self._user_id = user_id

    def authenticate(self, request: Request) -> UUID | None:
        return self._user_id

    def validate_csrf(self, request: Request, *, user_id: UUID) -> bool:
        return user_id == self._user_id


def _unit_of_work_factory(engine: Engine) -> UnitOfWorkFactory:
    session_factory = create_session_factory(engine)

    def factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return factory


def _client(
    postgres_engine: Engine,
    artifact_root: Path,
) -> tuple[TestClient, UnitOfWorkFactory, UUID]:
    unit_of_work_factory = _unit_of_work_factory(postgres_engine)
    with unit_of_work_factory() as unit_of_work:
        operator = unit_of_work.users.add_user(
            UserCreate(display_name="Annotation operator", roles={GlobalRole.operator})
        )
        team = unit_of_work.teams.add_team(
            TeamCreate(slug=f"annotation-{operator.id.hex}", display_name="Annotation team")
        )
        unit_of_work.teams.add_member(team.id, operator.id)
        unit_of_work.commit()
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit=CODE_GIT_COMMIT,
            dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
            artifact_root=artifact_root,
        ),
        unit_of_work_factory=unit_of_work_factory,
        authentication_backend=StaticAuthenticationBackend(operator.id),
    )
    return TestClient(application), unit_of_work_factory, operator.id


def _ready_snapshot_id(
    client: TestClient,
    unit_of_work_factory: UnitOfWorkFactory,
    artifact_root: Path,
    *,
    source: bytes = VALID_TEI,
    project_id: UUID | None = None,
) -> UUID:
    if project_id is None:
        project_response = client.post(
            "/api/v1/projects",
            json={
                "slug": f"review-{uuid4().hex}",
                "display_name": "Review endpoint fixture",
                "team_id": client.get("/api/v1/teams").json()["items"][0]["id"],
            },
        )
        project_id = UUID(project_response.json()["id"])
    snapshot_response = client.post(
        f"/api/v1/projects/{project_id}/snapshots",
        files={"source": ("register.xml", source, "application/xml")},
    )
    snapshot_id = UUID(snapshot_response.json()["id"])
    SnapshotImportExecutor(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=LocalArtifactStorage(artifact_root),
        parser=TeiPersonParser(),
        import_batch_record_count=1,
        clock=lambda: datetime(2026, 8, 14, 12, tzinfo=UTC),
    ).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=snapshot_id),
        attempt_count=1,
    )
    return snapshot_id


def test_annotations_are_attributable_append_only_and_revision_checked(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, unit_of_work_factory, reviewer_id = _client(postgres_engine, tmp_path)
    snapshot_id = _ready_snapshot_id(client, unit_of_work_factory, tmp_path)
    first_command = {
        "snapshot_id": str(snapshot_id),
        "tei_id": "p1",
        "action": ReviewAction.verify.value,
        "label": CanonicalLabel.female.value,
        "expected_revision": 0,
    }

    first_response = client.post("/api/v1/annotations", json=first_command)
    stale_response = client.post("/api/v1/annotations", json=first_command)

    assert first_response.status_code == 201
    first_body = first_response.json()
    assert first_body["reviewer_user_id"] == str(reviewer_id)
    assert first_body["resulting_revision"] == 1
    assert stale_response.status_code == 409
    stale_error = stale_response.json()["error"]
    assert stale_error["code"] == "annotation_conflict"
    assert stale_error["details"] == {"current_revision": 1}
    assert stale_error["request_id"] == stale_response.headers["x-request-id"]

    defer_response = client.post(
        "/api/v1/annotations",
        json={
            "snapshot_id": str(snapshot_id),
            "tei_id": "p1",
            "action": ReviewAction.defer.value,
            "expected_revision": 1,
        },
    )

    assert defer_response.status_code == 201
    defer_body = defer_response.json()
    assert defer_body["label"] is None
    assert defer_body["supersedes_annotation_id"] == first_body["id"]
    assert defer_body["resulting_revision"] == 2

    with unit_of_work_factory() as unit_of_work:
        state = unit_of_work.reviews.get_review_state(snapshot_id, "p1")
    assert state is not None
    assert state.revision == 2
    assert state.workflow_state is ReviewWorkflowState.deferred


def test_annotation_rejects_client_reviewer_and_missing_machine_result(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, unit_of_work_factory, reviewer_id = _client(postgres_engine, tmp_path)
    snapshot_id = _ready_snapshot_id(client, unit_of_work_factory, tmp_path)
    base_command = {
        "snapshot_id": str(snapshot_id),
        "tei_id": "p1",
        "action": ReviewAction.verify.value,
        "label": CanonicalLabel.female.value,
        "expected_revision": 0,
    }

    reviewer_response = client.post(
        "/api/v1/annotations",
        json={**base_command, "reviewer_user_id": str(reviewer_id)},
    )
    result_response = client.post(
        "/api/v1/annotations",
        json={**base_command, "aggregated_result_id": str(uuid4())},
    )

    assert reviewer_response.status_code == 422
    assert result_response.status_code == 404


def test_annotation_history_returns_the_attributed_chain_newest_first(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, unit_of_work_factory, reviewer_id = _client(postgres_engine, tmp_path)
    snapshot_id = _ready_snapshot_id(client, unit_of_work_factory, tmp_path)
    history_params = {"snapshot_id": str(snapshot_id), "tei_id": "p1"}

    unreviewed = client.get("/api/v1/annotations", params=history_params).json()
    for expected_revision, action, label in (
        (0, ReviewAction.verify, CanonicalLabel.female),
        (1, ReviewAction.correct, CanonicalLabel.male),
    ):
        response = client.post(
            "/api/v1/annotations",
            json={
                **history_params,
                "action": action.value,
                "label": label.value,
                "expected_revision": expected_revision,
            },
        )
        assert response.status_code == 201
    history_response = client.get("/api/v1/annotations", params=history_params)
    history = history_response.json()
    next_response = client.post(
        "/api/v1/annotations",
        json={
            **history_params,
            "action": ReviewAction.defer.value,
            "expected_revision": history["revision"],
        },
    )
    missing = client.get(
        "/api/v1/annotations", params={"snapshot_id": str(snapshot_id), "tei_id": "absent"}
    )

    assert (unreviewed["revision"], unreviewed["workflow_state"]) == (0, "unreviewed")
    assert unreviewed["annotations"] == []
    assert history_response.status_code == 200
    assert (history["revision"], history["workflow_state"]) == (2, "reviewed")
    assert [
        (item["resulting_revision"], item["action"], item["label"], item["reviewer_display_name"])
        for item in history["annotations"]
    ] == [
        (2, "correct", "male", "Annotation operator"),
        (1, "verify", "female", "Annotation operator"),
    ]
    assert {item["reviewer_user_id"] for item in history["annotations"]} == {str(reviewer_id)}
    assert history["current_annotation_id"] == history["annotations"][0]["id"]
    assert history["annotations"][0]["supersedes_annotation_id"] == history["annotations"][1]["id"]
    assert next_response.status_code == 201
    assert missing.status_code == 404


ANNOTATION_TEI = """<TEI xmlns="http://www.tei-c.org/ns/1.0">
<text><body><listPerson>
<person xml:id="p3"><persName type="reg"><surname>Percent% Under_score</surname></persName></person>
<person xml:id="p1"><persName type="reg"><forename>Ada</forename><surname>Müller</surname></persName></person>
<person xml:id="p2"><persName type="reg"><forename>Jules</forename><surname>Example</surname></persName></person>
</listPerson></body></text></TEI>""".encode()


def test_snapshot_annotation_items_paginate_and_search_without_classification(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, factory, _ = _client(postgres_engine, tmp_path)
    snapshot_id = _ready_snapshot_id(client, factory, tmp_path, source=ANNOTATION_TEI)
    path = f"/api/v1/snapshots/{snapshot_id}/annotation-items"

    first = client.get(path, params={"limit": 1}).json()
    second = client.get(path, params={"limit": 1, "cursor": first["next_cursor"]}).json()
    third = client.get(path, params={"limit": 1, "cursor": second["next_cursor"]}).json()
    exact = client.get(f"{path}/p3")

    assert [page["items"][0]["tei_id"] for page in (first, second, third)] == ["p1", "p2", "p3"]
    assert [page["has_more"] for page in (first, second, third)] == [True, True, False]
    assert third["next_cursor"] is None
    assert exact.status_code == 200
    assert exact.json() == third["items"][0]
    item = first["items"][0]
    assert (item["surname"], item["forenames"]) == ("Müller", ["Ada"])
    assert (item["review_revision"], item["workflow_state"]) == (0, "unreviewed")
    assert item["human_label"] is item["review_action"] is item["current_annotation_id"] is None
    assert "machine_label" not in item
    assert "certainty_tier" not in item
    for search, identifiers in ((" aDA ", ["p1"]), ("p2", ["p2"]), ("%", ["p3"]), ("_", ["p3"])):
        response = client.get(path, params={"q": search})
        assert response.status_code == 200
        assert [item["tei_id"] for item in response.json()["items"]] == identifiers
    assert client.get(f"{path}/absent").status_code == 404


def test_snapshot_annotation_items_project_current_decisions_and_keep_snapshots_separate(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, factory, _ = _client(postgres_engine, tmp_path)
    snapshot_id = _ready_snapshot_id(client, factory, tmp_path, source=ANNOTATION_TEI)
    path = f"/api/v1/snapshots/{snapshot_id}/annotation-items"
    command = {
        "snapshot_id": str(snapshot_id),
        "tei_id": "p1",
        "action": "correct",
        "label": "female",
        "expected_revision": 0,
    }
    annotation = client.post("/api/v1/annotations", json=command)
    assert annotation.status_code == 201
    assert annotation.json()["aggregated_result_id"] is None
    assert client.post("/api/v1/annotations", json=command).status_code == 409
    reviewed = client.get(path, params={"human_label": "female", "workflow_states": "reviewed"})
    assert [item["tei_id"] for item in reviewed.json()["items"]] == ["p1"]
    item = reviewed.json()["items"][0]
    assert (item["review_revision"], item["review_action"], item["human_label"]) == (
        1,
        "correct",
        "female",
    )
    assert item["current_annotation_id"] == annotation.json()["id"]

    defer = client.post(
        "/api/v1/annotations",
        json={
            "snapshot_id": str(snapshot_id),
            "tei_id": "p1",
            "action": "defer",
            "expected_revision": 1,
        },
    )
    assert defer.status_code == 201
    deferred = client.get(path, params={"workflow_states": "deferred"}).json()["items"]
    assert len(deferred) == 1
    assert (
        deferred[0]["review_revision"],
        deferred[0]["review_action"],
        deferred[0]["human_label"],
    ) == (2, "defer", None)
    assert client.get(path, params={"human_label": "female"}).json()["items"] == []
    unknown = client.post(
        "/api/v1/annotations", json={**command, "tei_id": "p2", "label": "unknown"}
    )
    assert unknown.status_code == 201
    assert [
        item["tei_id"]
        for item in client.get(path, params={"human_label": "unknown"}).json()["items"]
    ] == ["p2"]
    remaining = client.get(path, params={"workflow_states": ["unreviewed", "deferred"]})
    assert [item["tei_id"] for item in remaining.json()["items"]] == ["p1", "p3"]

    project_id = UUID(client.get(f"/api/v1/snapshots/{snapshot_id}").json()["project_id"])
    other_snapshot_id = _ready_snapshot_id(client, factory, tmp_path, project_id=project_id)
    independent = client.get(f"/api/v1/snapshots/{other_snapshot_id}/annotation-items/p1").json()
    assert independent["review_revision"] == 0
    assert independent["current_annotation_id"] is None


def test_snapshot_annotation_cursor_binds_every_filter_and_snapshot(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, factory, _ = _client(postgres_engine, tmp_path)
    snapshot_id = _ready_snapshot_id(client, factory, tmp_path, source=ANNOTATION_TEI)
    other_snapshot_id = _ready_snapshot_id(client, factory, tmp_path)
    path = f"/api/v1/snapshots/{snapshot_id}/annotation-items"
    cursor = client.get(path, params={"limit": 1}).json()["next_cursor"]
    assert cursor
    for changed in ({"q": "Ada"}, {"human_label": "female"}, {"workflow_states": "reviewed"}):
        response = client.get(path, params={"cursor": cursor, **changed})
        assert response.status_code == 422
        assert response.json()["error"]["details"] == {"reason": "invalid_cursor"}
    assert (
        client.get(
            f"/api/v1/snapshots/{other_snapshot_id}/annotation-items", params={"cursor": cursor}
        ).status_code
        == 422
    )
    assert client.get(path, params={"cursor": "broken"}).status_code == 422
    assert client.get(path, params={"q": "   "}).status_code == 422
    assert client.get(path, params={"workflow_states": ["reviewed", "reviewed"]}).status_code == 422


def test_snapshot_annotation_items_require_ready_snapshot_and_project_read_access(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, factory, _ = _client(postgres_engine, tmp_path)
    snapshot_id = _ready_snapshot_id(client, factory, tmp_path)
    snapshot = client.get(f"/api/v1/snapshots/{snapshot_id}").json()
    project_id = UUID(snapshot["project_id"])
    pending = client.post(
        f"/api/v1/projects/{project_id}/snapshots",
        files={"source": ("register.xml", VALID_TEI, "application/xml")},
    ).json()["id"]
    for suffix in ("", "/p1"):
        response = client.get(f"/api/v1/snapshots/{pending}/annotation-items{suffix}")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "resource_conflict"

    with factory() as unit_of_work:
        project = unit_of_work.projects.get_project(project_id)
        assert project is not None
        viewer = unit_of_work.users.add_user(UserCreate(display_name="Annotation viewer"))
        unit_of_work.teams.add_member(project.team.id, viewer.id)
        unit_of_work.access.set_member_role(project_id, viewer.id, ProjectRole.viewer)
        unit_of_work.commit()
    principal = CurrentUser(id=viewer.id, display_name=viewer.display_name, roles=viewer.roles)
    cast(FastAPI, client.app).dependency_overrides[require_authenticated_user] = lambda: principal
    cast(FastAPI, client.app).dependency_overrides[require_csrf_protection] = lambda: None
    path = f"/api/v1/snapshots/{snapshot_id}/annotation-items"
    assert client.get(path).status_code == 200
    assert client.get(f"{path}/p1").status_code == 200
    assert (
        client.post(
            "/api/v1/annotations",
            json={
                "snapshot_id": str(snapshot_id),
                "tei_id": "p1",
                "action": "correct",
                "label": "unknown",
                "expected_revision": 0,
            },
        ).status_code
        == 403
    )
    with factory() as unit_of_work:
        unit_of_work.access.remove_member(project_id, viewer.id)
        unit_of_work.commit()
    assert client.get(path).status_code == 404
    assert client.get(f"{path}/p1").status_code == 404
