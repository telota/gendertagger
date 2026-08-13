"""FastAPI dependency adapters for application-owned resources."""

from typing import cast

from fastapi import Request

from gendertagger.services.projects import ProjectService
from gendertagger.services.unit_of_work import UnitOfWorkFactory


def get_unit_of_work_factory(request: Request) -> UnitOfWorkFactory:
    """Return the process-scoped factory used by application services."""
    return cast(UnitOfWorkFactory, request.app.state.unit_of_work_factory)


def get_project_service(request: Request) -> ProjectService:
    """Return the composed project application service."""
    return cast(ProjectService, request.app.state.project_service)
