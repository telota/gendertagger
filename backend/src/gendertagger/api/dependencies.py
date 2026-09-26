"""FastAPI dependency adapters for application-owned resources."""

from typing import cast

from fastapi import Request

from gendertagger.api.settings import AppSettings
from gendertagger.services.admin_settings import AdminSettingsService
from gendertagger.services.aggregations import AggregationService
from gendertagger.services.annotations import AnnotationService
from gendertagger.services.authentication import AuthenticationService
from gendertagger.services.classification import DirectClassificationService
from gendertagger.services.evaluations import EvaluationService
from gendertagger.services.execution import RunScheduler
from gendertagger.services.exports import ExportService
from gendertagger.services.game_rounds import GameRoundService
from gendertagger.services.method_registry import MethodRegistry
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.services.project_access import ProjectAccessService
from gendertagger.services.projects import ProjectService
from gendertagger.services.review_items import ReviewItemService
from gendertagger.services.runs import RunService
from gendertagger.services.teams import TeamService
from gendertagger.services.user_administration import UserAdministrationService
from gendertagger.services.user_preferences import UserPreferencesService


def get_unit_of_work_factory(request: Request) -> UnitOfWorkFactory:
    """Return the process-scoped factory used by application services."""
    return cast(UnitOfWorkFactory, request.app.state.unit_of_work_factory)


def get_app_settings(request: Request) -> AppSettings:
    """Return the process-scoped, environment-backed application settings."""
    return cast(AppSettings, request.app.state.settings)


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


def get_game_round_service(request: Request) -> GameRoundService:
    """Return the composed game-round application service."""
    return cast(GameRoundService, request.app.state.game_round_service)


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


def get_user_administration_service(request: Request) -> UserAdministrationService:
    """Return the composed local-account administration service."""
    return cast(UserAdministrationService, request.app.state.user_administration_service)


def get_team_service(request: Request) -> TeamService:
    """Return the composed direct-team administration service."""
    return cast(TeamService, request.app.state.team_service)


def get_admin_settings_service(request: Request) -> AdminSettingsService:
    """Return the composed administrative deployment-settings service."""
    return cast(AdminSettingsService, request.app.state.admin_settings_service)


def get_user_preferences_service(request: Request) -> UserPreferencesService:
    """Return the composed account-owned presentation preferences service."""
    return cast(UserPreferencesService, request.app.state.user_preferences_service)
