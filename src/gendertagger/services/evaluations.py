"""Application use cases for independently rerunnable evaluations."""

from collections.abc import Callable
from uuid import UUID

from gendertagger.models.api import CursorPage
from gendertagger.models.common import UtcDatetime
from gendertagger.models.dispatch import EvaluationDispatchCreate
from gendertagger.models.evaluation import (
    EvaluationCreateRequest,
    EvaluationDefinition,
    EvaluationDefinitionId,
    EvaluationExecution,
    EvaluationExecutionCreate,
    EvaluationTaskMessage,
)
from gendertagger.models.queues import CPU_QUEUE
from gendertagger.services.artifact_storage import ArtifactStorage
from gendertagger.services.pagination import (
    CursorCodec,
    decode_creation_position,
    newest_first_page,
)
from gendertagger.services.persistence_errors import ResourceNotFoundError
from gendertagger.services.unit_of_work import UnitOfWorkFactory

Clock = Callable[[], UtcDatetime]

_EVALUATION_DEFINITIONS: dict[EvaluationDefinitionId, EvaluationDefinition] = {
    EvaluationDefinitionId.gnd_benchmark_v1: EvaluationDefinition(),
}


def resolve_evaluation_definition(definition_id: EvaluationDefinitionId) -> EvaluationDefinition:
    """Resolve a versioned evaluation definition identifier to its configuration."""
    return _EVALUATION_DEFINITIONS[definition_id]


class EvaluationService:
    """Persist durable evaluation commands and read immutable reports."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        artifact_storage: ArtifactStorage,
        cursor_codec: CursorCodec,
        clock: Clock,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._artifact_storage = artifact_storage
        self._cursor_codec = cursor_codec
        self._clock = clock

    def create_evaluation(self, command: EvaluationCreateRequest) -> EvaluationExecution:
        """Persist one evaluation and its durable dispatch intent atomically."""
        definition = resolve_evaluation_definition(command.definition)
        with self._unit_of_work_factory() as unit_of_work:
            evaluation = unit_of_work.evaluations.add_evaluation(
                EvaluationExecutionCreate(
                    run_id=command.run_id,
                    definition=command.definition,
                    resolved_config=definition.model_dump(mode="json"),
                    method_execution_ids=command.method_execution_ids,
                    aggregation_execution_id=command.aggregation_execution_id,
                )
            )
            unit_of_work.dispatches.ensure_dispatch(
                EvaluationDispatchCreate(
                    evaluation_execution_id=evaluation.id,
                    queue_name=CPU_QUEUE,
                    payload=EvaluationTaskMessage(
                        evaluation_execution_id=evaluation.id,
                    ),
                    available_at=self._clock(),
                )
            )
            evaluation = unit_of_work.evaluations.mark_evaluation_queued(evaluation.id)
            unit_of_work.commit()
        return evaluation

    def get_evaluation(self, evaluation_id: UUID) -> EvaluationExecution:
        """Return one evaluation execution or raise a not-found failure."""
        with self._unit_of_work_factory() as unit_of_work:
            evaluation = unit_of_work.evaluations.get_evaluation(evaluation_id)
        if evaluation is None:
            msg = f"evaluation execution {evaluation_id} does not exist"
            raise ResourceNotFoundError(msg)
        return evaluation

    def list_evaluations(
        self,
        run_id: UUID,
        *,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[EvaluationExecution]:
        """Return one newest-first opaque-cursor page of a run's evaluations."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        resource = f"run_evaluations:{run_id}"
        after = decode_creation_position(self._cursor_codec, cursor, resource=resource)
        with self._unit_of_work_factory() as unit_of_work:
            if unit_of_work.runs.get_run(run_id) is None:
                msg = f"run {run_id} does not exist"
                raise ResourceNotFoundError(msg)
            evaluations = unit_of_work.evaluations.list_evaluations(
                run_id,
                limit=limit + 1,
                after=after,
            )
        return newest_first_page(self._cursor_codec, evaluations, limit=limit, resource=resource)

    def get_report(self, evaluation_id: UUID) -> tuple[bytes, str]:
        """Return the completed evaluation's report bytes and media type."""
        evaluation = self.get_evaluation(evaluation_id)
        if evaluation.report_artifact_id is None:
            msg = f"evaluation execution {evaluation_id} has no report artifact"
            raise ResourceNotFoundError(msg)
        with self._unit_of_work_factory() as unit_of_work:
            artifact = unit_of_work.artifacts.get_artifact(evaluation.report_artifact_id)
        if artifact is None:
            msg = f"artifact {evaluation.report_artifact_id} does not exist"
            raise ResourceNotFoundError(msg)
        with self._artifact_storage.open(artifact.storage_uri) as source:
            return source.read(), artifact.media_type
