"""FastAPI dependency adapters for application-owned resources."""

from typing import cast

from fastapi import Request

from gendertagger.services.unit_of_work import UnitOfWorkFactory


def get_unit_of_work_factory(request: Request) -> UnitOfWorkFactory:
    """Return the process-scoped factory used by application services."""
    return cast(UnitOfWorkFactory, request.app.state.unit_of_work_factory)
