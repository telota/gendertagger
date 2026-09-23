from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from gendertagger.db.project_repository import SqlAlchemyProjectRepository
from gendertagger.models.project import ProjectCreate
from gendertagger.services.ports.persistence_errors import ResourceNotFoundError

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


def test_set_working_aggregation_rejects_an_unknown_project(db_session: Session) -> None:
    """The HTTP route's ``ProjectAccessGuard`` already hides an unknown project with 404 before
    the service is called, so this defensive repository branch is only reachable directly."""
    repository = SqlAlchemyProjectRepository(db_session)
    missing_project_id = uuid4()

    with pytest.raises(ResourceNotFoundError, match=str(missing_project_id)):
        repository.set_working_aggregation(missing_project_id, aggregation_execution_id=None)


def test_set_working_aggregation_rejects_an_unknown_aggregation(db_session: Session) -> None:
    repository = SqlAlchemyProjectRepository(db_session)
    project = repository.add_project(
        ProjectCreate(slug=f"working-agg-{uuid4().hex}", display_name="Working aggregation fixture")
    )
    missing_aggregation_id = uuid4()

    with pytest.raises(ResourceNotFoundError, match=str(missing_aggregation_id)):
        repository.set_working_aggregation(
            project.id,
            aggregation_execution_id=missing_aggregation_id,
        )
