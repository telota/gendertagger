"""Application orchestration for executable benchmark evaluations."""

from collections.abc import Callable
from datetime import datetime
from io import BytesIO
from uuid import UUID

from pydantic import ValidationError

from gendertagger.evaluation.report import EvaluationInputError, build_report
from gendertagger.models.artifact import Artifact, ArtifactCreate
from gendertagger.models.evaluation import (
    EvaluationDefinition,
    EvaluationExecution,
    EvaluationTaskMessage,
)
from gendertagger.models.lifecycle import EvaluationExecutionStatus
from gendertagger.services.diagnostics import sanitized_diagnostic
from gendertagger.services.ports.artifact_storage import ArtifactStorage
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

Clock = Callable[[], datetime]

DEFAULT_MAX_EVALUATION_ATTEMPTS = 3
_EVALUATION_REPORT_LOGICAL_TYPE = "evaluation_report"
_EVALUATION_REPORT_MEDIA_TYPE = "application/json"


class TransientEvaluationError(RuntimeError):
    """Raised when evaluation execution should be retried after rollback."""


class EvaluationExecutor:
    """Assess and atomically persist one complete evaluation report.

    The claim, computed report artifact, and terminal lifecycle transition
    share one transaction. A worker crash therefore exposes either the prior
    claimable resource or the complete final report, never a committed
    partial evaluation.
    """

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        artifact_storage: ArtifactStorage,
        max_report_bytes: int,
        clock: Clock,
    ) -> None:
        if max_report_bytes <= 0:
            msg = "evaluation report byte limit must be positive"
            raise ValueError(msg)
        self._unit_of_work_factory = unit_of_work_factory
        self._artifact_storage = artifact_storage
        self._max_report_bytes = max_report_bytes
        self._clock = clock

    def execute(
        self,
        message: EvaluationTaskMessage,
        *,
        attempt_count: int,
        max_attempts: int = DEFAULT_MAX_EVALUATION_ATTEMPTS,
    ) -> EvaluationExecution:
        """Idempotently execute one evaluation with bounded retry policy.

        Invalid or incomplete persisted evidence is terminally persisted.
        Unclassified failures roll back and request a retry until the final
        attempt, when a fresh claim records the sanitized failure diagnostic.

        Args:
            message: Identifier-only task envelope.
            attempt_count: One-based delivery attempt number.
            max_attempts: Maximum attempts before an unclassified error becomes
                terminal.

        Returns:
            The completed, failed, or previously claimed evaluation resource.

        Raises:
            TransientEvaluationError: If an unclassified failure occurred and
                another attempt remains.
            ValueError: If attempt counts are not positive.
        """
        if attempt_count <= 0:
            msg = "attempt_count must be positive"
            raise ValueError(msg)
        if max_attempts <= 0:
            msg = "max_attempts must be positive"
            raise ValueError(msg)

        try:
            return self._execute_once(message)
        except Exception as error:
            if attempt_count < max_attempts:
                msg = (
                    f"evaluation {message.evaluation_execution_id} failed "
                    f"on attempt {attempt_count}"
                )
                raise TransientEvaluationError(msg) from error
            return self._fail_after_rollback(message, error)

    def _execute_once(self, message: EvaluationTaskMessage) -> EvaluationExecution:
        with self._unit_of_work_factory() as unit_of_work:
            evaluation = unit_of_work.evaluations.claim_evaluation(
                message.evaluation_execution_id,
                started_at=self._clock(),
            )
            if evaluation is None:
                return self._existing_evaluation(unit_of_work, message)

            try:
                report_bytes = self._build_report_bytes(unit_of_work, evaluation)
            except (
                EvaluationInputError,
                InvalidResourceStateError,
                ValidationError,
            ) as error:
                failed = self._mark_failed(unit_of_work, evaluation.id, error)
                unit_of_work.commit()
                return failed

            artifact = self._store_report(unit_of_work, evaluation, report_bytes)
            completed = unit_of_work.evaluations.mark_evaluation_finished(
                evaluation.id,
                status=EvaluationExecutionStatus.completed,
                finished_at=self._clock(),
                report_artifact_id=artifact.id,
            )
            unit_of_work.commit()
            return completed

    def _fail_after_rollback(
        self,
        message: EvaluationTaskMessage,
        error: BaseException,
    ) -> EvaluationExecution:
        with self._unit_of_work_factory() as unit_of_work:
            evaluation = unit_of_work.evaluations.claim_evaluation(
                message.evaluation_execution_id,
                started_at=self._clock(),
            )
            if evaluation is None:
                return self._existing_evaluation(unit_of_work, message)
            failed = self._mark_failed(unit_of_work, evaluation.id, error)
            unit_of_work.commit()
            return failed

    def _build_report_bytes(
        self,
        unit_of_work: UnitOfWork,
        evaluation: EvaluationExecution,
    ) -> bytes:
        definition = EvaluationDefinition.model_validate(evaluation.resolved_config)
        inputs = unit_of_work.evaluations.load_evaluation_inputs(evaluation.id)
        report = build_report(
            inputs.corpus,
            definition,
            aggregated_results=inputs.aggregated_results,
            human_reviewed_count=inputs.human_reviewed_count,
            human_correction_count=inputs.human_correction_count,
        )
        return report.model_dump_json().encode("utf-8")

    def _store_report(
        self,
        unit_of_work: UnitOfWork,
        evaluation: EvaluationExecution,
        report_bytes: bytes,
    ) -> Artifact:
        stored = self._artifact_storage.store(
            BytesIO(report_bytes),
            max_byte_size=self._max_report_bytes,
        )
        return unit_of_work.artifacts.add_artifact(
            ArtifactCreate(
                logical_type=_EVALUATION_REPORT_LOGICAL_TYPE,
                storage_uri=stored.storage_uri,
                sha256=stored.sha256,
                byte_size=stored.byte_size,
                media_type=_EVALUATION_REPORT_MEDIA_TYPE,
                run_id=evaluation.run_id,
                evaluation_execution_id=evaluation.id,
            )
        )

    def _mark_failed(
        self,
        unit_of_work: UnitOfWork,
        evaluation_execution_id: UUID,
        error: BaseException,
    ) -> EvaluationExecution:
        return unit_of_work.evaluations.mark_evaluation_finished(
            evaluation_execution_id,
            status=EvaluationExecutionStatus.failed,
            finished_at=self._clock(),
            failure_class=type(error).__name__,
            failure_diagnostic=sanitized_diagnostic(error),
        )

    @staticmethod
    def _existing_evaluation(
        unit_of_work: UnitOfWork,
        message: EvaluationTaskMessage,
    ) -> EvaluationExecution:
        evaluation = unit_of_work.evaluations.get_evaluation(message.evaluation_execution_id)
        if evaluation is None:
            msg = f"evaluation execution {message.evaluation_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        return evaluation
