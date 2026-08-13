"""FastAPI dependency adapters for application-owned resources."""

from typing import cast

from fastapi import Request

from gendertagger.services.aggregations import AggregationService
from gendertagger.services.annotations import AnnotationService
from gendertagger.services.method_registry import MethodRegistry
from gendertagger.services.projects import ProjectService
from gendertagger.services.review_items import ReviewItemService
from gendertagger.services.runs import RunService
from gendertagger.services.unit_of_work import UnitOfWorkFactory


def get_unit_of_work_factory(request: Request) -> UnitOfWorkFactory:
    """Return the process-scoped factory used by application services."""
    return cast(UnitOfWorkFactory, request.app.state.unit_of_work_factory)


def get_project_service(request: Request) -> ProjectService:
    """Return the composed project application service."""
    return cast(ProjectService, request.app.state.project_service)


def get_aggregation_service(request: Request) -> AggregationService:
    """Return the composed aggregation application service."""
    return cast(AggregationService, request.app.state.aggregation_service)


def get_annotation_service(request: Request) -> AnnotationService:
    """Return the composed annotation application service."""
    return cast(AnnotationService, request.app.state.annotation_service)


def get_method_registry(request: Request) -> MethodRegistry:
    """Return the process-scoped server method registry."""
    return cast(MethodRegistry, request.app.state.method_registry)


def get_run_service(request: Request) -> RunService:
    """Return the composed run application service."""
    return cast(RunService, request.app.state.run_service)


def get_review_item_service(request: Request) -> ReviewItemService:
    """Return the composed review-item query service."""
    return cast(ReviewItemService, request.app.state.review_item_service)
