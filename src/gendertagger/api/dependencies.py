"""FastAPI dependency adapters for application-owned resources."""

from typing import cast

from fastapi import Request

from gendertagger.services.aggregations import AggregationService
from gendertagger.services.annotations import AnnotationService
from gendertagger.services.authentication import AuthenticationService
from gendertagger.services.classification import DirectClassificationService
from gendertagger.services.evaluations import EvaluationService
from gendertagger.services.execution import RunScheduler
from gendertagger.services.exports import ExportService
from gendertagger.services.method_registry import MethodRegistry
from gendertagger.services.project_access import ProjectAccessService
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


def get_project_access_service(request: Request) -> ProjectAccessService:
    """Return the composed project authorization and membership service."""
    return cast(ProjectAccessService, request.app.state.project_access_service)


def get_aggregation_service(request: Request) -> AggregationService:
    """Return the composed aggregation application service."""
    return cast(AggregationService, request.app.state.aggregation_service)


def get_evaluation_service(request: Request) -> EvaluationService:
    """Return the composed evaluation application service."""
    return cast(EvaluationService, request.app.state.evaluation_service)


def get_export_service(request: Request) -> ExportService:
    """Return the composed export application service."""
    return cast(ExportService, request.app.state.export_service)


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


def get_run_scheduler(request: Request) -> RunScheduler:
    """Return the composed run-scheduling application service."""
    return cast(RunScheduler, request.app.state.run_scheduler)


def get_classification_service(request: Request) -> DirectClassificationService:
    """Return the composed direct classification application service."""
    return cast(DirectClassificationService, request.app.state.classification_service)


def get_authentication_service(request: Request) -> AuthenticationService:
    """Return the composed local-account authentication application service."""
    return cast(AuthenticationService, request.app.state.authentication_service)
